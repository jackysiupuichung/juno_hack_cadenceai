"""Build the next-visit brief from a visit and its check-ins.

The hero artifact, on the terminal, with no database and no frontend. Point it
at a summary fixture and whatever check-ins the interval produced; a run with
no check-ins is worth doing too, because a brief that honestly reports an empty
interval is the behaviour that distinguishes this from a scribe.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from capture.brief import BriefError, build_brief, render
from capture.interval import IntervalError, compute_interval_facts, load_context


class Command(BaseCommand):
    help = "Generate the next-visit brief from a summary and its check-ins."

    def add_arguments(self, parser):
        parser.add_argument("summary", help="A *.summary.json fixture.")
        parser.add_argument(
            "--check-ins",
            nargs="*",
            default=[],
            help="Check-in JSON files, oldest first. Omit for an empty interval.",
        )
        parser.add_argument("--condition", default="hypothyroidism")
        parser.add_argument("--visit-date", default="")
        parser.add_argument("--today", default="")
        parser.add_argument(
            "--week",
            type=int,
            default=12,
            help="Weeks into the interval, when no visit date is given.",
        )
        parser.add_argument("-o", "--out", default="")

    def handle(self, *args, **options):
        summary_path = Path(options["summary"])
        if not summary_path.is_file():
            raise CommandError(f"No such file: {summary_path}")

        body = json.loads(summary_path.read_text())
        summary = body.get("summary", body)

        today = (
            datetime.strptime(options["today"], "%Y-%m-%d").date()
            if options["today"]
            else date.today()
        )
        visit_date = (
            datetime.strptime(options["visit_date"], "%Y-%m-%d").date()
            if options["visit_date"]
            else today - timedelta(weeks=options["week"])
        )

        check_ins = []
        for path in options["check_ins"]:
            p = Path(path)
            if not p.is_file():
                raise CommandError(f"No such check-in: {p}")
            record = json.loads(p.read_text())
            # Written by run_check_in with its week in a _meta sidecar.
            record.setdefault("week", (record.get("_meta") or {}).get("week", 0))
            check_ins.append(record)
        check_ins.sort(key=lambda c: c.get("week", 0))

        try:
            context = load_context(options["condition"])
            facts = compute_interval_facts(
                summary=summary,
                context=context,
                visit_date=visit_date,
                today=today,
                prior_check_ins=check_ins,
            )
        except IntervalError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Week {facts.week} of the interval, "
                f"{len(check_ins)} check-in(s) recorded"
            )
        )

        try:
            brief = build_brief(facts=facts, check_ins=check_ins)
        except BriefError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("\n" + render(brief) + "\n")

        out = (
            Path(options["out"])
            if options["out"]
            else summary_path.with_suffix(".brief.json")
        )
        out.write_text(
            json.dumps(
                {
                    "_meta": {
                        "week": facts.week,
                        "visit_date": facts.visit_date.isoformat(),
                        "generated_for": facts.today.isoformat(),
                        "check_ins": [c.get("week") for c in check_ins],
                        "usage": brief.usage,
                    },
                    **brief.data,
                },
                indent=2,
            )
            + "\n"
        )
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))
