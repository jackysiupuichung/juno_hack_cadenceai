"""Speech-to-text for visit capture, via ElevenLabs Scribe.

Turns a recording of a consultation into a speaker-labelled transcript. This is
the front of the loop: everything downstream (summary, commitments, brief) reads
the transcript this produces.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

MODEL_ID = "scribe_v1"

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


def _client() -> ElevenLabs:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return ElevenLabs(api_key=api_key)


def _group_into_utterances(words) -> list[Utterance]:
    """Collapse Scribe's word-level output into per-speaker utterances.

    Scribe returns one entry per word with a speaker_id. Consecutive words from
    the same speaker are one utterance; a speaker change starts a new one.
    """
    utterances: list[Utterance] = []

    for word in words or []:
        # Spacing entries carry no speaker of their own — append to the current
        # utterance so we don't fragment on every gap between words.
        word_type = getattr(word, "type", "word")
        text = getattr(word, "text", "") or ""
        if word_type == "spacing":
            if utterances:
                utterances[-1].text += text
            continue

        speaker = getattr(word, "speaker_id", None) or "speaker_0"
        start = getattr(word, "start", None)
        end = getattr(word, "end", None)

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


def transcribe_file(
    audio_path: str | Path,
    *,
    num_speakers: int | None = 2,
    language_code: str | None = "eng",
    keyterms: list[str] | None = None,
) -> Transcript:
    """Transcribe a recorded visit.

    Args:
        audio_path: Audio file to transcribe.
        num_speakers: Expected speaker count. A consultation is usually two
            (doctor, patient); pass None to let Scribe decide.
        language_code: ISO code, or None to auto-detect.
        keyterms: Vocabulary hints. Defaults to VISIT_KEYTERMS.

    Returns:
        A Transcript with speaker-labelled utterances.
    """
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"No audio file at {path}")

    kwargs = {
        "model_id": MODEL_ID,
        "diarize": True,
        "tag_audio_events": False,
        "timestamps_granularity": "word",
        "keyterms": keyterms if keyterms is not None else VISIT_KEYTERMS,
    }
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    if language_code is not None:
        kwargs["language_code"] = language_code

    with path.open("rb") as audio:
        result = _client().speech_to_text.convert(file=audio, **kwargs)

    return Transcript(
        text=getattr(result, "text", "") or "",
        utterances=_group_into_utterances(getattr(result, "words", None)),
        language_code=getattr(result, "language_code", None),
    )


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
