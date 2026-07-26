"""Tests for loop.auth: the one part of the account system that doesn't
touch Supabase, so it's the one part covered by unit tests here rather than
by hand against the live database."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from . import auth


class PasswordHashingTests(SimpleTestCase):
    def test_round_trip(self):
        hashed = auth.hash_password("correct horse battery staple")
        self.assertTrue(auth.verify_password("correct horse battery staple", hashed))

    def test_wrong_password_rejected(self):
        hashed = auth.hash_password("correct horse battery staple")
        self.assertFalse(auth.verify_password("wrong password", hashed))

    def test_hash_is_not_the_plaintext(self):
        hashed = auth.hash_password("hunter2")
        self.assertNotEqual(hashed, "hunter2")


class TokenTests(SimpleTestCase):
    def test_round_trip(self):
        token = auth.issue_token("patient-123")
        self.assertEqual(auth.decode_token(token), "patient-123")

    def test_refuses_to_sign_with_the_public_dev_default(self):
        with patch.object(auth.settings, "SECRET_KEY", auth._INSECURE_DEFAULT_KEY):
            with self.assertRaises(RuntimeError):
                auth.issue_token("patient-123")

    def test_tampered_token_rejected(self):
        token = auth.issue_token("patient-123")
        self.assertIsNone(auth.decode_token(token + "x"))

    def test_garbage_rejected(self):
        self.assertIsNone(auth.decode_token("not-a-token"))

    def test_expired_token_rejected(self):
        with patch.object(auth, "TOKEN_TTL_SECONDS", -1):
            token = auth.issue_token("patient-123")
        self.assertIsNone(auth.decode_token(token))


class PatientIdFromRequestTests(SimpleTestCase):
    def _request(self, header: str | None) -> Request:
        factory = APIRequestFactory()
        extra = {"HTTP_AUTHORIZATION": header} if header else {}
        return Request(factory.get("/", **extra))

    def test_missing_header(self):
        self.assertIsNone(auth.patient_id_from_request(self._request(None)))

    def test_malformed_header(self):
        self.assertIsNone(auth.patient_id_from_request(self._request("Token abc")))

    def test_valid_bearer_token(self):
        token = auth.issue_token("patient-456")
        request = self._request(f"Bearer {token}")
        self.assertEqual(auth.patient_id_from_request(request), "patient-456")
