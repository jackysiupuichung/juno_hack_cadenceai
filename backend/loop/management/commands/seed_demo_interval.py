"""Seed a full 12-week interval — the loop, not just the visit.

`seed_demo_offline` writes one visit, one check-in where everything went fine,
and a brief. That is enough to see the schemas land and not enough to see the
product: a brief assembled from a single call on which nothing went wrong is a
summary with extra steps, and the whole claim is that the brief is MADE OF
interval data.

This command replays fixtures/demo_interval.json — five calls across twelve
weeks against the same demo consultation — so what lands in Supabase is an
interval with the texture a real one has:

  - the prescription collected nine days late
  - a dose the consultation never stated, closed by a pharmacy label that
    disagrees with what the patient remembers being told
  - the tablet taken at half two rather than the agreed morning slot, on the
    patient's own reasoning
  - doses missed in the middle weeks for a reason that has nothing to do with
    the drug
  - a blood test that was ordered and silently never happened
  - two over-replacement symptoms, reported two weeks apart, neither connected
    to the medication by the patient — the cluster the product exists to catch,
    assembled one call at a time

Calls are replayed in order rather than written as an end state, because the
order is the point. The medication thread accumulates across them, which is the
behaviour the persistence layer was added for and the thing worth demonstrating
against a real database rather than a unit test.

No LLM calls and no API key: everything here is fixture data. For a live run
through Claude, use `seed_demo`.

    manage.py seed_demo_interval [--date YYYY-MM-DD] [--condition-name Thyroid]

`--date` is the CONSULTATION date; every call is placed relative to it. It
defaults to twelve weeks ago so the interval reads as just-completed and the
brief is generated at the moment a patient would actually want one.
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from capture import events as ev
from capture import medication
from capture.caretaker import CaretakerContext
from capture.interval import load_context
from capture.redflags import evaluate_flags

from ... import caretaker_repo, medication_repo, repo

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "demo_consultation.json"
SUMMARY_PATH = FIXTURES_DIR / "demo_consultation.summary.json"
INTERVAL_PATH = FIXTURES_DIR / "demo_interval.json"

# The interval's length, and so the default age of the consultation. Twelve
# weeks is past the guideline's seven-week blood test plus its grace period,
# which is what makes the missing test overdue rather than merely outstanding —
# the distinction the brief exists to draw.
INTERVAL_WEEKS = 12


def _strip_comments(value):
    """Drop the _comment keys the fixture uses to explain itself.

    The fixture is written to be read by a person as much as parsed by this
    command — the reasoning behind each call is the part worth reviewing. None
    of it should reach the database.
    """
    if isinstance(value, dict):
        return {k: _strip_comments(v) for k, v in value.items() if k != "_comment"}
    if isinstance(value, list):
        return [_strip_comments(v) for v in value]
    return value


class Command(BaseCommand):
    help = "Seed a full 12-week interval — five calls, a medication thread, and a caretaker context. No LLM calls."

    def add_arguments(self, parser):
        parser.add_argument("--condition-name", default="Thyroid")
        parser.add_argument(
            "--care-setting",
            default="specialist",
            choices=["gp", "hospital", "emergency", "specialist"],
        )
        parser.add_argument(
            "--date",
            default=None,
            help=f"Consultation date, YYYY-MM-DD. Defaults to {INTERVAL_WEEKS} weeks ago.",
        )

    def handle(self, *args, **options):
        for path in (TRANSCRIPT_PATH, SUMMARY_PATH, INTERVAL_PATH):
            if not path.exists():
                raise CommandError(f"Fixture not found at {path}")

        transcript = json.loads(TRANSCRIPT_PATH.read_text()).get("dialogue", "")
        summary = json.loads(SUMMARY_PATH.read_text())["summary"]
        interval = _strip_comments(json.loads(INTERVAL_PATH.read_text()))

        visit_date = (
            date_cls.fromisoformat(options["date"])
            if options["date"]
            else date_cls.today() - timedelta(weeks=INTERVAL_WEEKS)
        )

        patient = repo.get_or_create_patient()

        # --- The person ------------------------------------------------------
        # First, because it is the only thing here that is not about a
        # condition: it describes who is being rung, and it would still be true
        # if this consultation had never happened.
        person = CaretakerContext(**interval["caretaker_context"])
        caretaker_repo.save_caretaker_context(patient["id"], person)
        self.stdout.write(
            self.style.SUCCESS(
                f"caretaker context — {person.address_as() or 'unnamed'}, "
                f"{person.call_length_preference} calls, "
                f"{len(person.medication_barriers)} medication barrier(s)"
            )
        )

        condition = next(
            (
                c
                for c in repo.list_conditions(patient["id"])
                if c["name"] == options["condition_name"]
            ),
            None,
        ) or repo.create_condition(patient["id"], options["condition_name"])

        # --- The consultation ------------------------------------------------
        visit = repo.create_visit(
            condition["id"],
            date=visit_date.isoformat(),
            care_setting=options["care_setting"],
            clinician_name="",
            organisation="",
            transcript=transcript,
            summary=summary,
        )
        commitments = repo.create_commitments(visit["id"], summary.get("commitments", []))
        by_text = {c["text"]: c for c in commitments}

        # The medication thread as the consultation left it: clinician-sourced,
        # confirmed, and with "very low dose" stored as the gap it is. The calls
        # below are what close it.
        meds = medication.from_summary(summary)
        med_rows = medication_repo.create_medications(visit["id"], meds)
        self.stdout.write(
            self.style.SUCCESS(
                f"visit {visit['id']} — {len(commitments)} commitment(s), "
                f"{len(med_rows)} medication(s), gaps: "
                f"{', '.join(meds[0].gaps) if meds else 'n/a'}"
            )
        )

        # --- The visit's own events ------------------------------------------
        repo.create_events(
            [
                ev.to_row(
                    ev.Event(
                        kind="visit",
                        label=f"Consultation ({options['care_setting']})",
                        occurred_at=visit_date,
                        precision="day",
                        source="consultation",
                        recorded_at=visit_date,
                    ),
                    condition_id=condition["id"],
                    visit_id=visit["id"],
                )
            ]
        )

        # --- The calls -------------------------------------------------------
        # Replayed in order. Mentions accumulate across all of them, because a
        # cluster that assembles across two calls is invisible to anything that
        # only looks at the current one.
        context = load_context()
        med_state = meds[0] if meds else None
        med_id = med_rows[0]["id"] if med_rows else None
        all_mentions: list[dict] = []

        for call in interval["check_ins"]:
            call_date = visit_date + timedelta(days=call["day"])

            outcome_rows = []
            for outcome in call["raw"]["outcomes"]:
                commitment = by_text.get(outcome["commitment_text"])
                if not commitment:
                    self.stderr.write(
                        self.style.WARNING(
                            f"  week {call['week']}: no commitment matching "
                            f"{outcome['commitment_text'][:60]!r} — skipped"
                        )
                    )
                    continue
                outcome_rows.append(
                    {
                        "commitment_id": commitment["id"],
                        "status": outcome["status"],
                        "patient_words": outcome["patient_words"],
                        "note": outcome["note"],
                    }
                )

            raw = {
                "outcomes": outcome_rows,
                "unprompted_reports": call["raw"]["unprompted_reports"],
                "questions_for_doctor": call["raw"]["questions_for_doctor"],
            }
            # Not part of check_in.schema.json, but the record needs them: a
            # mention dropped here is a red flag that never fires, and a score
            # dropped here is a series that means nothing.
            if call["symptom_mentions"]:
                raw["symptom_mentions"] = [
                    {**m, "week": call["week"]} for m in call["symptom_mentions"]
                ]
            if call["symptom_scores"]:
                raw["symptom_scores"] = [
                    {**s, "week": call["week"]} for s in call["symptom_scores"]
                ]

            check_in = repo.create_check_in(
                condition["id"],
                date=call_date.isoformat(),
                transcript=call["transcript"],
                raw=raw,
            )
            repo.create_outcomes(check_in["id"], outcome_rows)

            # A commitment's column follows the answer the call produced.
            # "partial" and "not_done" stay open on purpose — they are exactly
            # what the next call should be chasing.
            for row in outcome_rows:
                if row["status"] != "unknown":
                    repo.update_commitment_status(row["commitment_id"], row["status"])

            # The chronology. Dates the patient gave, which are not the date of
            # the call that surfaced them — a symptom reported at week 11 that
            # began at week 9 is a two-week gap worth seeing.
            event_rows = [
                ev.to_row(
                    ev.Event(
                        kind=e["kind"],
                        label=e["label"],
                        occurred_at=visit_date + timedelta(days=e["occurred_at_day"]),
                        precision=e["precision"],
                        source=e["source"],
                        patient_words=e.get("patient_words", ""),
                        context_ids=tuple(e.get("context_ids", ())),
                        recorded_at=call_date,
                    ),
                    condition_id=condition["id"],
                    check_in_id=check_in["id"],
                )
                for e in call["events"]
            ]
            event_rows.append(
                ev.to_row(
                    ev.Event(
                        kind="check_in",
                        label=f"Check-in call (week {call['week']})",
                        occurred_at=call_date,
                        precision="day",
                        source="derived",
                        recorded_at=call_date,
                    ),
                    condition_id=condition["id"],
                    check_in_id=check_in["id"],
                )
            )
            repo.create_events(event_rows)

            # The medication thread moves forward and is written back, rather
            # than being recomputed from the summary next time. This is the
            # whole reason the table exists.
            if med_state is not None and med_id:
                med_state = self._apply(med_state, call.get("medication_updates", {}))
                medication_repo.save_medication(med_id, med_state)

            all_mentions.extend(
                {**m, "week": call["week"]} for m in call["symptom_mentions"]
            )
            fired = evaluate_flags(context, all_mentions, week=call["week"])

            fired_note = (
                f" — FLAG FIRED: {', '.join(f.flag_id for f in fired)}" if fired else ""
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"  week {call['week']:>2} (day {call['day']:>2}) — "
                    f"{len(outcome_rows)} outcome(s), "
                    f"{len(call['symptom_mentions'])} mention(s), "
                    f"{len(event_rows)} event(s){fired_note}"
                )
            )

        # --- Where the thread ended up ---------------------------------------
        if med_state is not None:
            day = medication.days_since(visit_date, visit_date + timedelta(weeks=INTERVAL_WEEKS))
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nmedication thread at week {INTERVAL_WEEKS}: "
                    f"{med_state.as_line()}; collection {med_state.collection.value}; "
                    f"adherence {med_state.adherence.value}; "
                    f"reminder {med_state.reminder_time or 'unset'}; "
                    f"gaps {med_state.gaps or 'none'}"
                )
            )
            for note in med_state.notes:
                self.stdout.write(f"  note: {note}")
            for task in medication.due_tasks([med_state], day=day):
                self.stdout.write(f"  still outstanding: [{task.kind}] {task.intent}")

        still_open = repo.get_open_commitments(condition["id"])
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(still_open)} commitment(s) still open at the end of the interval:"
            )
        )
        for c in still_open:
            self.stdout.write(f"  [{c['status']}] {c['text'][:80]}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Condition {condition['id']} ({condition['name']}), "
                f"consultation {visit_date.isoformat()}.\n"
                f"Generate the brief with: POST /api/brief {{\"condition_id\": \"{condition['id']}\"}}"
            )
        )

    def _apply(self, med, updates: dict):
        """Move the medication thread on by one call.

        Label handling goes through medication.apply_label / confirm_label
        rather than assigning the fields, so the seeded data exercises the same
        gap-fill-never-overwrite rule the live path does — including recording
        the disagreement between the label and what the clinician said, which is
        one of the more interesting lines in the resulting brief.
        """
        from dataclasses import replace

        from capture.medication import Adherence, Collection

        extracted = updates.get("label_extracted")
        if extracted:
            med = medication.apply_label(med, extracted)
            if updates.get("label_confirmed"):
                med = medication.confirm_label(med, accepted=True)

        simple = {}
        if "collection" in updates:
            simple["collection"] = Collection(updates["collection"])
        if "adherence" in updates:
            simple["adherence"] = Adherence(updates["adherence"])
        for key in ("first_dose_taken", "reminder_time", "label_seen", "last_chased_day"):
            if key in updates:
                simple[key] = updates[key]

        return replace(med, **simple) if simple else med
