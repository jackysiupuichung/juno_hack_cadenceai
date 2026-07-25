"""API endpoints for visit capture."""

from __future__ import annotations

import httpx
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .transcribe import transcribe_audio

# Anything larger is almost certainly not a consultation recording, and we'd
# rather reject it than pay to transcribe it.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def transcribe(request):
    """Transcribe an uploaded consultation recording.

    Expects multipart with an `audio` file. Optional fields: `speakers`
    (integer, 0 to auto-detect) and `language` ('auto' to detect).

    Returns the transcript as speaker-labelled utterances.
    """
    upload = request.FILES.get("audio")
    if upload is None:
        return Response(
            {"error": "No audio file provided. Send multipart with an 'audio' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if upload.size == 0:
        return Response(
            {"error": "The uploaded audio file is empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if upload.size > MAX_UPLOAD_BYTES:
        return Response(
            {
                "error": (
                    f"Audio file is too large ({upload.size} bytes). "
                    f"Limit is {MAX_UPLOAD_BYTES} bytes."
                )
            },
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    raw_speakers = request.data.get("speakers", "2")
    try:
        speakers = int(raw_speakers)
    except (TypeError, ValueError):
        return Response(
            {"error": f"'speakers' must be an integer, got {raw_speakers!r}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    language = request.data.get("language", "eng")

    try:
        transcript = transcribe_audio(
            upload.file,
            upload.name or "audio.mp3",
            num_speakers=speakers or None,
            language_code=None if language == "auto" else language,
        )
    except RuntimeError as exc:
        # Missing API key — a deployment problem, not the caller's fault.
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except httpx.HTTPStatusError as exc:
        # Surface the upstream reason; the transcription itself failed.
        return Response(
            {
                "error": "Transcription failed upstream.",
                "upstream_status": exc.response.status_code,
                "upstream_detail": exc.response.text[:500],
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except httpx.RequestError as exc:
        return Response(
            {"error": f"Could not reach the transcription service: {exc}"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    return _transcript_response(transcript)


def _transcript_response(transcript) -> Response:
    return Response(
        {
            "text": transcript.text,
            "language_code": transcript.language_code,
            # Role-labelled, which is what the summary stage reads.
            "dialogue": transcript.as_dialogue(),
            "speakers": [
                {"label": label, "role": transcript.role_for(label)}
                for label in transcript.speakers
            ],
            "role_confidence": (
                transcript.roles.confidence if transcript.roles else "none"
            ),
            "duration_seconds": transcript.duration,
            "utterances": [
                {
                    "speaker": u.speaker,
                    "role": transcript.role_for(u.speaker),
                    "text": u.text,
                    "start": u.start,
                    "end": u.end,
                }
                for u in transcript.utterances
            ],
        }
    )
