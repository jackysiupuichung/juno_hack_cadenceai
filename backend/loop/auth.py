"""Patient accounts: email + password, a signed token, no session table.

Django's own auth app runs against sqlite (see config/settings.py's
DATABASES), a different store than Supabase where the patient record lives —
so this doesn't reuse django.contrib.auth's User model. It reuses Django's
password hasher (PBKDF2, already configured, no new dependency) and signs a
small JWT with the same SECRET_KEY Django already trusts, rather than adding
a sessions table this size of project doesn't need.
"""

from __future__ import annotations

import time
from functools import wraps

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import status
from rest_framework.response import Response

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days: a phone that stays signed in.

# Django's own placeholder when DJANGO_SECRET_KEY is unset (see
# config/settings.py) — public, in this repo's source, and in every other
# Django project's too. Signing a real patient's auth token with it would mean
# anyone who has read this file can forge a login for anyone. See DJANGO_SECRET_KEY
# in .env.example. issue_token refuses outright rather than signing anyway.
_INSECURE_DEFAULT_KEY = "django-insecure-dev-only-do-not-use-in-production"


def hash_password(password: str) -> str:
    return make_password(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password(password, password_hash)


def issue_token(patient_id: str) -> str:
    if settings.SECRET_KEY == _INSECURE_DEFAULT_KEY:
        raise RuntimeError(
            "DJANGO_SECRET_KEY is not set. Refusing to sign an auth token with "
            "the public Django dev default — set DJANGO_SECRET_KEY in .env "
            "(see .env.example for how to generate one)."
        )
    payload = {"patient_id": patient_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> str | None:
    """The patient_id a token names, or None for anything expired, forged,
    or malformed. Never raises — a bad token is just an anonymous request."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload.get("patient_id")


def patient_id_from_request(request) -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return decode_token(header[len("Bearer "):])


def require_auth(view_func):
    """Resolve the calling patient from the Authorization header, or 401.

    Sets request.patient_id rather than threading it through every view's
    arguments — the same request object DRF already hands the view.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        patient_id = patient_id_from_request(request)
        if not patient_id:
            return Response(
                {"error": "Sign in required."}, status=status.HTTP_401_UNAUTHORIZED
            )
        request.patient_id = patient_id
        return view_func(request, *args, **kwargs)

    return wrapped
