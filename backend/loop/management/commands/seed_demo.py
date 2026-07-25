"""
Seed Supabase with the demo consultation fixture, run through the full real
pipeline: summarise -> check-in -> brief. Exercises all three LLM calls and
all three schemas/*.json shapes with one command, so the data can be
inspected directly in Supabase without needing the frontend.

The fixture is already-transcribed dialogue (from demo_consultation.m4a via
ElevenLabs Scribe) — this chains it into the summary stage without
re-transcribing, so it's cheap to re-run while iterating.

Requires ANTHROPIC_API_KEY and SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY to be
set for real (the migrations in supabase/migrations/ must already be applied).
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ... import repo
from ...services import (
    BRIEF_SYSTEM_PROMPT,
    CHECKIN_SYSTEM_PROMPT,
    SUMMARISE_SYSTEM_PROMPT,
    LLMJSONError,
    call_llm_json,
)

FIXTURE_PATH = Path(__file__).resolve().parents[4] / "fixtures" / "demo_consultation.json"

# Statuses a check-in can settle a commitment into. "partial" belongs here —
# it is a real answer, and leaving it out left the commitment at "pending" as
# though nobody had ever asked. Kept in step with views.RESOLVED_STATUSES.
RESOLVED_STATUSES = {"done", "not_done", "partial", "changed"}

# A plausible patient-only voice check-in, written to touch every commitment
# without hardcoding what those commitments will say (they're extracted by
# Claude from the fixture and can vary slightly run to run).
CHECKIN_NARRATIVE_TEMPLATE = (
    "Hi, it's me checking in about my thyroid follow-up. "
    "Regarding \"{text}\" — I've mostly kept up with that, it's going okay, "
    "no real problems. "
)


def _build_synthetic_checkin_transcript(commitments: list[dict]) -> str:
    parts = [CHECKIN_NARRATIVE_TEMPLATE.format(text=c["text"]) for c in commitments]
    if not parts:
        return "Hi, just a general check-in — nothing new to report since my last visit."
    return " ".join(parts) + " Overall I'm feeling a bit better than before."


class Command(BaseCommand):
    help = (
        "Run fixtures/demo_consultation.json through summarise -> check-in -> brief "
        "via Claude and seed all of it into Supabase."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--care-setting",
            default="specialist",
            choices=["gp", "hospital", "emergency", "specialist"],
        )
        parser.add_argument("--clinician-name", default="")
        parser.add_argument("--organisation", default="")
        parser.add_argument("--date", default=None, help="Visit date, YYYY-MM-DD, defaults to today")
        parser.add_argument(
            "--condition-name",
            default="Thyroid",
            help="Condition to seed the visit under (created if it doesn't exist)",
        )
        parser.add_argument(
            "--skip-checkin",
            action="store_true",
            help="Only seed the visit summary; skip the check-in and brief steps.",
        )

    def handle(self, *args, **options):
        if not FIXTURE_PATH.exists():
            raise CommandError(f"Fixture not found at {FIXTURE_PATH}")

        fixture = json.loads(FIXTURE_PATH.read_text())
        transcript = fixture.get("dialogue")
        if not transcript:
            raise CommandError("Fixture has no 'dialogue' field to summarise.")

        # --- A. visit_summary.schema.json ---------------------------------
        self.stdout.write("1/3 Summarising the fixture transcript...")
        try:
            summary = call_llm_json(SUMMARISE_SYSTEM_PROMPT, transcript)
        except LLMJSONError as exc:
            raise CommandError(f"Claude did not return valid JSON: {exc.raw_text}") from exc

        p = repo.get_or_create_patient()
        condition = next(
            (c for c in repo.list_conditions(p["id"]) if c["name"] == options["condition_name"]),
            None,
        ) or repo.create_condition(p["id"], options["condition_name"])

        visit_date = options["date"] or date_cls.today().isoformat()
        visit = repo.create_visit(
            condition["id"],
            date=visit_date,
            care_setting=options["care_setting"],
            clinician_name=options["clinician_name"],
            organisation=options["organisation"],
            transcript=transcript,
            summary=summary,
        )
        commitments = repo.create_commitments(visit["id"], summary.get("commitments", []))
        self.stdout.write(self.style.SUCCESS(f"   visit {visit['id']} — {len(commitments)} commitment(s)"))

        if options["skip_checkin"]:
            return

        # --- B. check_in.schema.json ---------------------------------------
        self.stdout.write("2/3 Running a synthetic check-in through Claude...")
        checkin_transcript = _build_synthetic_checkin_transcript(commitments)
        commitments_context = [{"commitment_id": c["id"], "text": c["text"]} for c in commitments]
        user_content = f"Transcript:\n{checkin_transcript}\n\nOpen commitments:\n{commitments_context}"
        try:
            mapped = call_llm_json(CHECKIN_SYSTEM_PROMPT, user_content)
        except LLMJSONError as exc:
            raise CommandError(f"Claude did not return valid JSON: {exc.raw_text}") from exc

        check_in_date = (date_cls.fromisoformat(visit_date) + timedelta(days=14)).isoformat()
        check_in = repo.create_check_in(
            condition["id"], date=check_in_date, transcript=checkin_transcript, raw=mapped
        )
        outcome_rows = mapped.get("outcomes", [])
        outcomes = repo.create_outcomes(check_in["id"], outcome_rows)
        for row in outcome_rows:
            if row.get("status") in RESOLVED_STATUSES:
                repo.update_commitment_status(row["commitment_id"], row["status"])
        self.stdout.write(self.style.SUCCESS(f"   check-in {check_in['id']} — {len(outcomes)} outcome(s)"))

        # --- C. brief.schema.json --------------------------------------------
        self.stdout.write("3/3 Generating the next-visit brief...")
        fresh_commitments = repo.get_commitments_for_visit(visit["id"])
        fresh_outcomes = repo.get_outcomes_for_commitments([c["id"] for c in fresh_commitments])
        payload = {
            "visit_summary": summary,
            "commitments": [
                {"id": c["id"], "text": c["text"], "status": c["status"]} for c in fresh_commitments
            ],
            "check_in_outcomes": [
                {
                    "commitment_id": o["commitment_id"],
                    "date": (o.get("check_ins") or {}).get("date"),
                    "status": o["status"],
                    "patient_words": o["patient_words"],
                    "note": o["note"],
                }
                for o in fresh_outcomes
            ],
        }
        try:
            content = call_llm_json(BRIEF_SYSTEM_PROMPT, str(payload))
        except LLMJSONError as exc:
            raise CommandError(f"Claude did not return valid JSON: {exc.raw_text}") from exc

        brief = repo.create_brief(condition["id"], content)
        self.stdout.write(self.style.SUCCESS(f"   brief {brief['id']}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Condition: {condition['id']} ({condition['name']})"))
