"""Transcribe an audio file and save the result as a JSON fixture.

Transcription costs money and takes minutes; the downstream stages (summary,
commitment extraction, brief) need a transcript to develop against. Saving one
lets those stages iterate without re-hitting ElevenLabs on every run.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from capture.transcribe import transcribe_file


class Command(BaseCommand):
    help = "Transcribe an audio file and write the transcript as JSON."

    def add_arguments(self, parser):
        parser.add_argument("audio", help="path to the audio file")
        parser.add_argument(
            "-o",
            "--out",
            help="where to write the JSON (default: alongside the audio, .json)",
        )
        parser.add_argument(
            "--speakers",
            type=int,
            default=0,
            help="expected speaker count (0 to auto-detect, the default)",
        )
        parser.add_argument(
            "--language",
            default="auto",
            help="ISO language code, or 'auto' to detect (the default)",
        )

    def handle(self, *args, **options):
        audio_path = Path(options["audio"])
        if not audio_path.is_file():
            raise CommandError(f"No audio file at {audio_path}")

        out_path = (
            Path(options["out"])
            if options["out"]
            else audio_path.with_suffix(".json")
        )

        self.stdout.write(f"Transcribing {audio_path.name}…")

        language = options["language"]
        try:
            transcript = transcribe_file(
                audio_path,
                num_speakers=options["speakers"] or None,
                language_code=None if language == "auto" else language,
            )
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        payload = {
            "source_audio": audio_path.name,
            "language_code": transcript.language_code,
            "duration_seconds": transcript.duration,
            "role_confidence": (
                transcript.roles.confidence if transcript.roles else "none"
            ),
            "speakers": [
                {"label": label, "role": transcript.role_for(label)}
                for label in transcript.speakers
            ],
            "dialogue": transcript.as_dialogue(),
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
            "text": transcript.text,
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n")

        roles = ", ".join(
            f"{s['label']}={s['role']}" for s in payload["speakers"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {out_path} — {len(payload['utterances'])} turns, "
                f"{payload['duration_seconds']:.0f}s, {roles} "
                f"({payload['role_confidence']} confidence)"
            )
        )
