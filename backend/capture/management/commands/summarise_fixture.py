"""Summarise a saved transcript fixture and write the result as JSON.

Chains the capture output into the summary stage without re-transcribing, so
the commitment extraction can be iterated on cheaply.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from capture.summarise import SummariseError, summarise_transcript


class Command(BaseCommand):
    help = "Summarise a transcript fixture and write the visit summary as JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "transcript",
            help="path to a transcript JSON fixture (from transcribe_fixture)",
        )
        parser.add_argument(
            "-o",
            "--out",
            help="where to write the summary (default: <name>.summary.json)",
        )

    def handle(self, *args, **options):
        path = Path(options["transcript"])
        if not path.is_file():
            raise CommandError(f"No transcript fixture at {path}")

        try:
            fixture = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}") from exc

        dialogue = fixture.get("dialogue")
        if not dialogue:
            raise CommandError(f"{path} has no 'dialogue' field to summarise")

        out_path = (
            Path(options["out"])
            if options["out"]
            else path.with_suffix(".summary.json")
        )

        self.stdout.write(f"Summarising {path.name}…")

        try:
            summary = summarise_transcript(dialogue)
        except SummariseError as exc:
            raise CommandError(str(exc)) from exc

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary.data, indent=2) + "\n")

        commitments = summary.commitments
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {out_path} — {len(commitments)} commitments, "
                f"{len(summary.medications)} medications, "
                f"{len(summary.red_flags)} red flags "
                f"({summary.usage.get('output_tokens', 0)} output tokens)"
            )
        )

        for c in commitments:
            timeframe = f" [{c['timeframe']}]" if c.get("timeframe") else ""
            self.stdout.write(f"  · ({c['type']}){timeframe} {c['text']}")
