"""Run a check-in against a fixture, with a simulated or live patient.

The agent brain, exercised from the terminal with no database and no voice
layer. `--patient stdin` lets you be the patient, which is the fastest way to
see whether the agent is asking sensible things; `--patient llm` runs the
experiment the product rests on — hidden symptoms the patient will not
volunteer, and whether the agent thinks to ask.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from capture import checkin, medication, simulate
from capture.checkin import CheckInError, run_check_in
from capture.interval import (
    IntervalError,
    compute_interval_facts,
    load_context,
)

# The over-replacement cluster: symptoms that look nothing like an underactive
# thyroid, so the patient does not connect them and will not raise them.
DEFAULT_HIDDEN = [
    "trouble sleeping",
    "feeling hot when others do not, or sweating more",
]


class Command(BaseCommand):
    help = "Run a check-in against a visit summary fixture."

    def add_arguments(self, parser):
        parser.add_argument("summary", help="A *.summary.json fixture.")
        parser.add_argument(
            "--patient",
            default="stdin",
            help="stdin | llm | scripted:<path>. Default: stdin.",
        )
        parser.add_argument("--condition", default="hypothyroidism")
        parser.add_argument(
            "--visit-date",
            default="",
            help="ISO date of the consultation. Default: --week weeks before today.",
        )
        parser.add_argument("--today", default="", help="ISO date to evaluate as.")
        parser.add_argument(
            "--week",
            type=int,
            default=6,
            help="Weeks into the interval, when no visit date is given. Default: 6.",
        )
        parser.add_argument(
            "--day",
            type=int,
            default=None,
            help=(
                "Days into the interval. Overrides --week and selects the "
                "day-after first contact when 0 or 1."
            ),
        )
        parser.add_argument(
            "--check-ins",
            nargs="*",
            default=[],
            help="Earlier check-in JSON files, oldest first.",
        )
        parser.add_argument(
            "--hidden",
            nargs="*",
            default=None,
            help="Symptoms the llm patient will not volunteer. Default: the cluster.",
        )
        parser.add_argument("--max-turns", type=int, default=8)
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
        if options["visit_date"]:
            visit_date = datetime.strptime(options["visit_date"], "%Y-%m-%d").date()
        elif options["day"] is not None:
            visit_date = today - timedelta(days=options["day"])
        else:
            visit_date = today - timedelta(weeks=options["week"])

        # Only carried when it says something a week cannot. An ordinary week-six
        # check-in has no meaningful day, and stamping one on the record would be
        # false precision the brief would then have to reason about.
        elapsed = medication.days_since(visit_date, today)
        day = options["day"] if options["day"] is not None else (
            elapsed if elapsed <= medication.ADHERENCE_CHECK_DAYS else None
        )

        prior = []
        for path in options["check_ins"]:
            prior.append(json.loads(Path(path).read_text()))

        try:
            context = load_context(options["condition"])
            facts = compute_interval_facts(
                summary=summary,
                context=context,
                visit_date=visit_date,
                today=today,
                prior_check_ins=prior,
            )
        except IntervalError as exc:
            raise CommandError(str(exc)) from exc

        medications = medication.from_summary(summary)
        patient = self._patient(options)

        if day is not None and day <= checkin.FIRST_CONTACT_MAX_DAY:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"Day {day} — first contact after the consultation "
                    f"({facts.visit_date} → {facts.today}), "
                    f"{len(medications)} medication(s) prescribed"
                )
            )
        else:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"Week {facts.week} of the interval "
                    f"({facts.visit_date} → {facts.today}), "
                    f"{len(facts.open_commitments)} open commitment(s)"
                )
            )

        for med in medications:
            if med.gaps:
                self.stdout.write(
                    f"  {med.display_name}: not established — {', '.join(med.gaps)}"
                )
        if isinstance(patient, simulate.LlmPatient) and patient.hidden_symptoms:
            self.stdout.write("Patient is withholding, unless asked directly:")
            for symptom in patient.hidden_symptoms:
                self.stdout.write(f"  · {symptom}")
        self.stdout.write("")

        try:
            check_in = run_check_in(
                facts=facts,
                context=context,
                patient=patient,
                max_turns=options["max_turns"],
                medications=medications,
                day=day,
            )
        except CheckInError as exc:
            raise CommandError(str(exc)) from exc

        self._report(check_in, patient)

        if options["out"]:
            out = Path(options["out"])
        elif check_in.is_first_contact:
            out = summary_path.with_suffix(".checkin-d1.json")
        else:
            out = summary_path.with_suffix(f".checkin-w{facts.week}.json")
        out.write_text(
            json.dumps(
                {
                    "_meta": {
                        "week": check_in.week,
                        "day": check_in.day,
                        "first_contact": check_in.is_first_contact,
                        "visit_date": facts.visit_date.isoformat(),
                        "date": facts.today.isoformat(),
                        "ended_because": check_in.ended_because,
                        "covered": check_in.covered,
                        "reasoning": check_in.reasoning,
                        "fired_flags": [f.summary for f in check_in.fired_flags],
                        "usage": check_in.usage,
                    },
                    "symptom_mentions": check_in.symptom_mentions,
                    "transcript": check_in.transcript,
                    **check_in.data,
                },
                indent=2,
            )
            + "\n"
        )
        self.stdout.write(self.style.SUCCESS(f"\nWrote {out}"))

    def _patient(self, options):
        spec = options["patient"]
        if spec == "stdin":
            return simulate.StdinPatient()
        if spec == "llm":
            hidden = options["hidden"]
            return simulate.LlmPatient(
                hidden_symptoms=DEFAULT_HIDDEN if hidden is None else hidden
            )
        if spec.startswith("scripted:"):
            path = Path(spec.split(":", 1)[1])
            if not path.is_file():
                raise CommandError(f"No such script: {path}")
            return simulate.ScriptedPatient.from_file(path)
        raise CommandError(f"Unknown --patient {spec!r}. Use stdin | llm | scripted:<path>.")

    def _report(self, check_in, patient):
        self.stdout.write(self.style.MIGRATE_HEADING("\nThe call"))
        for line, why in zip(
            [t for t in check_in.transcript if t["role"] == "agent"],
            check_in.reasoning,
        ):
            self.stdout.write(f"  AGENT: {line['text']}")
            if why:
                self.stdout.write(self.style.HTTP_INFO(f"         ({why})"))
        self.stdout.write("")

        if check_in.symptom_mentions:
            self.stdout.write(self.style.MIGRATE_HEADING("Symptoms recorded"))
            for m in check_in.symptom_mentions:
                self.stdout.write(f"  · {m['watch_for']} — \"{m['patient_words']}\"")

        if check_in.fired_flags:
            self.stdout.write(self.style.WARNING("\nRed flags fired"))
            for flag in check_in.fired_flags:
                self.stdout.write(self.style.WARNING(f"  ! {flag.summary}"))

        if check_in.outcomes:
            self.stdout.write(self.style.MIGRATE_HEADING("\nCommitment outcomes"))
            for o in check_in.outcomes:
                self.stdout.write(
                    f"  [{o['commitment_id']}] {o['status']} — \"{o['patient_words']}\""
                )

        if check_in.data.get("questions_for_doctor"):
            self.stdout.write(self.style.MIGRATE_HEADING("\nFor the doctor"))
            for q in check_in.data["questions_for_doctor"]:
                self.stdout.write(f"  ? {q}")

        self.stdout.write(f"\nEnded: {check_in.ended_because}")
