"""
Seed Supabase with the demo consultation, WITHOUT calling any LLM.

Uses fixtures/demo_consultation.summary.json — a real visit_summary.schema.json
-shaped output already generated (by a teammate, via Codex) from
fixtures/demo_consultation.json — directly, and pairs it with a hand-written
but schema-conformant check-in and brief so all three schemas
(visit_summary / check_in / brief) land in the database in one shot.

This exists so the team can inspect real rows in Supabase for schema review
without needing an ANTHROPIC_API_KEY / CODEX_API_KEY on hand. For a live run
through the actual Claude/Codex pipeline, use `seed_demo` instead.

Requires only SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (and the migrations in
supabase/migrations/ already applied).
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ... import repo

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "demo_consultation.json"
SUMMARY_PATH = FIXTURES_DIR / "demo_consultation.summary.json"

# A plausible ~2-week check-in, hand-written to match what a patient would
# plausibly report against the four commitments in demo_consultation.summary.json.
# Kept as data here (not generated) so this command needs no LLM call.
CHECKIN_TRANSCRIPT = (
    "Hi, just checking in about my thyroid appointment. I've been taking the "
    "tablet every morning around 7:30, on an empty stomach, like the doctor "
    "said — no problems there. I picked up the prescription from the pharmacy "
    "already. My heart's been totally normal, no racing or feeling anxious, so "
    "no issues on that front. Still waiting on the three-month review, nothing "
    "to report there yet. Honestly my skin isn't as dry as before and I've had "
    "a bit more energy."
)

# Maps commitment `text` (as it appears in the generated summary) to the
# outcome status/patient_words/note this check-in reports for it.
CHECKIN_OUTCOMES_BY_COMMITMENT_TEXT = {
    "You will take your thyroid replacement medication every morning around 7:30–8:00 am on an empty stomach, ideally at the same time each day, with a glass of water.": {
        "status": "done",
        "patient_words": "I've been taking the tablet every morning around 7:30, on an empty stomach",
        "note": "Consistent adherence reported.",
    },
    "You will pick up the thyroid replacement medication prescription the doctor sends.": {
        "status": "done",
        "patient_words": "I picked up the prescription from the pharmacy already",
        "note": "",
    },
    "You will seek urgent help if your heart is beating really fast or you feel very anxious while on the tablets.": {
        "status": "done",
        "patient_words": "My heart's been totally normal, no racing or feeling anxious",
        "note": "No red-flag symptoms reported.",
    },
    "You will have a review in 3 months to see how the medication has helped.": {
        "status": "unknown",
        "patient_words": "",
        "note": "Not yet due.",
    },
}

UNPROMPTED_REPORTS = ["Skin less dry than before", "Slightly more energy than before"]
QUESTIONS_FOR_DOCTOR: list[str] = []


class Command(BaseCommand):
    help = (
        "Seed the demo consultation into Supabase using the pre-generated summary "
        "fixture and a hand-written check-in/brief — no LLM calls, no API key needed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--care-setting",
            default="specialist",
            choices=["gp", "hospital", "emergency", "specialist"],
        )
        parser.add_argument("--condition-name", default="Thyroid")
        parser.add_argument("--date", default=None, help="Visit date, YYYY-MM-DD, defaults to today")

    def handle(self, *args, **options):
        if not TRANSCRIPT_PATH.exists():
            raise CommandError(f"Fixture not found at {TRANSCRIPT_PATH}")
        if not SUMMARY_PATH.exists():
            raise CommandError(f"Fixture not found at {SUMMARY_PATH}")

        transcript = json.loads(TRANSCRIPT_PATH.read_text()).get("dialogue", "")
        summary = json.loads(SUMMARY_PATH.read_text())["summary"]

        # --- A. visit_summary.schema.json -----------------------------------
        p = repo.get_or_create_patient()
        condition = next(
            (c for c in repo.list_conditions(p["id"]) if c["name"] == options["condition_name"]),
            None,
        ) or repo.create_condition(p["id"], options["condition_name"], disease_context_id="hypothyroidism")

        visit_date = options["date"] or date_cls.today().isoformat()
        visit = repo.create_visit(
            p["id"],
            condition_id=condition["id"],
            date=visit_date,
            care_setting=options["care_setting"],
            clinician_name="",
            organisation="",
            transcript=transcript,
            summary=summary,
        )
        commitments = repo.create_commitments(visit["id"], summary.get("commitments", []))
        self.stdout.write(self.style.SUCCESS(f"1/3 visit {visit['id']} — {len(commitments)} commitment(s)"))

        # --- B. check_in.schema.json ------------------------------------------
        check_in_date = (date_cls.fromisoformat(visit_date) + timedelta(days=14)).isoformat()
        outcome_rows = []
        for c in commitments:
            mapped = CHECKIN_OUTCOMES_BY_COMMITMENT_TEXT.get(c["text"])
            if mapped:
                outcome_rows.append({"commitment_id": c["id"], **mapped})

        raw = {
            "outcomes": outcome_rows,
            "unprompted_reports": UNPROMPTED_REPORTS,
            "questions_for_doctor": QUESTIONS_FOR_DOCTOR,
        }
        check_in = repo.create_check_in(
            condition["id"], date=check_in_date, transcript=CHECKIN_TRANSCRIPT, raw=raw
        )
        outcomes = repo.create_outcomes(check_in["id"], outcome_rows)
        for row in outcome_rows:
            if row["status"] in ("done", "not_done", "changed"):
                repo.update_commitment_status(row["commitment_id"], row["status"])
        self.stdout.write(self.style.SUCCESS(f"2/3 check-in {check_in['id']} — {len(outcomes)} outcome(s)"))

        # --- C. brief.schema.json ------------------------------------------------
        content = {
            "agreed": [{"commitment_id": c["id"], "text": c["text"]} for c in commitments],
            "did": [
                {
                    "commitment_id": c["id"],
                    "text": c["text"],
                    "status": CHECKIN_OUTCOMES_BY_COMMITMENT_TEXT.get(c["text"], {}).get(
                        "status", "unknown"
                    ),
                }
                for c in commitments
            ],
            "happened": [
                {"text": "Skin less dry and slightly more energy reported", "approx_timing": "around week two"},
                {"text": "No racing heart or anxiety symptoms reported", "approx_timing": "around week two"},
            ],
            "changed": [
                {"text": "Energy levels", "direction": "better"},
                {"text": "Skin dryness", "direction": "better"},
            ],
            "open_questions": [],
            "gaps": ["No data yet on the 3-month follow-up review, which has not occurred."],
        }
        brief = repo.create_brief(condition["id"], content)
        self.stdout.write(self.style.SUCCESS(f"3/3 brief {brief['id']}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Condition: {condition['id']} ({condition['name']})"))
