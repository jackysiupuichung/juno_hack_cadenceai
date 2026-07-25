"""Speech-to-text for visit capture, via ElevenLabs Scribe.

Turns a recording of a consultation into a speaker-labelled transcript. This is
the front of the loop: everything downstream (summary, commitments, brief) reads
the transcript this produces.
"""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

MODEL_ID = "scribe_v1"
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

# Clinical vocabulary Scribe would otherwise mangle. Wrong drug names and
# wrong conditions are the failure mode that matters most here, so bias the
# decoder toward the terms our wedge population actually hears in a visit.
VISIT_KEYTERMS = [
    "POTS",
    "postural orthostatic tachycardia syndrome",
    "ME/CFS",
    "myalgic encephalomyelitis",
    "dysautonomia",
    "tachycardia",
    "orthostatic",
    "fludrocortisone",
    "midodrine",
    "propranolol",
    "ivabradine",
    "beta blocker",
    "electrolytes",
    "tilt table test",
    "Holter monitor",
    "syncope",
    "presyncope",
    "flare",
    "titrate",
    "milligrams",
]


@dataclass
class Utterance:
    """One speaker's continuous stretch of speech."""

    speaker: str
    text: str
    start: float | None
    end: float | None


@dataclass
class Transcript:
    """A transcribed visit."""

    text: str
    utterances: list[Utterance]
    language_code: str | None

    def as_dialogue(self) -> str:
        """Render as `SPEAKER: text` lines, which is what the LLM stages read."""
        return "\n".join(f"{u.speaker}: {u.text}" for u in self.utterances)


def _api_key() -> str:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return api_key


def _field(item, name: str, default=None):
    """Read a field from a dict or an object, whichever the caller passed."""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _group_into_utterances(words) -> list[Utterance]:
    """Collapse Scribe's word-level output into per-speaker utterances.

    Scribe returns one entry per word with a speaker_id. Consecutive words from
    the same speaker are one utterance; a speaker change starts a new one.
    """
    utterances: list[Utterance] = []

    for word in words or []:
        # Spacing entries carry no speaker of their own — append to the current
        # utterance so we don't fragment on every gap between words.
        word_type = _field(word, "type", "word")
        text = _field(word, "text", "") or ""
        if word_type == "spacing":
            if utterances:
                utterances[-1].text += text
            continue

        speaker = _field(word, "speaker_id") or "speaker_0"
        start = _field(word, "start")
        end = _field(word, "end")

        if utterances and utterances[-1].speaker == speaker:
            current = utterances[-1]
            current.text += text
            current.end = end if end is not None else current.end
        else:
            utterances.append(
                Utterance(speaker=speaker, text=text, start=start, end=end)
            )

    for utterance in utterances:
        utterance.text = utterance.text.strip()

    return [u for u in utterances if u.text]


def transcribe_audio(
    audio,
    filename: str = "audio.mp3",
    *,
    num_speakers: int | None = 2,
    language_code: str | None = "eng",
    keyterms: list[str] | None = None,
) -> Transcript:
    """Transcribe a recorded visit from an open binary stream.

    Args:
        audio: File-like object opened in binary mode (an upload, or an open
            file). Not closed by this function.
        filename: Name used to derive the content type.
        num_speakers: Expected speaker count. A consultation is usually two
            (doctor, patient); pass None to let Scribe decide.
        language_code: ISO code, or None to auto-detect.
        keyterms: Vocabulary hints. Defaults to VISIT_KEYTERMS.

    Returns:
        A Transcript with speaker-labelled utterances.
    """
    # Posted as multipart rather than through the SDK: the SDK JSON-encodes
    # `keyterms` into a single form value, which the API rejects (the literal
    # brackets and quotes read as forbidden characters in one long keyterm).
    # The API expects one repeated `keyterms` field per term.
    form: dict[str, object] = {
        "model_id": MODEL_ID,
        "diarize": "true",
        "tag_audio_events": "false",
        "timestamps_granularity": "word",
    }
    if num_speakers is not None:
        form["num_speakers"] = str(num_speakers)
    if language_code is not None:
        form["language_code"] = language_code

    # A list value makes httpx emit one form field per item.
    form["keyterms"] = list(keyterms if keyterms is not None else VISIT_KEYTERMS)

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    response = httpx.post(
        STT_URL,
        headers={"xi-api-key": _api_key()},
        files={"file": (filename, audio, content_type)},
        data=form,
        timeout=600,
    )
    response.raise_for_status()
    result = response.json()

    return Transcript(
        text=_field(result, "text", "") or "",
        utterances=_group_into_utterances(_field(result, "words")),
        language_code=_field(result, "language_code"),
    )


def transcribe_file(audio_path: str | Path, **kwargs) -> Transcript:
    """Transcribe a recorded visit from a path on disk."""
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"No audio file at {path}")

    with path.open("rb") as audio:
        return transcribe_audio(audio, path.name, **kwargs)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe a visit recording.")
    parser.add_argument("audio", help="path to the audio file")
    parser.add_argument(
        "--speakers",
        type=int,
        default=2,
        help="expected speaker count (0 to auto-detect)",
    )
    parser.add_argument(
        "--language", default="eng", help="ISO language code, or 'auto' to detect"
    )
    args = parser.parse_args()

    transcript = transcribe_file(
        args.audio,
        num_speakers=args.speakers or None,
        language_code=None if args.language == "auto" else args.language,
    )

    print(transcript.as_dialogue() or transcript.text)


if __name__ == "__main__":
    main()
