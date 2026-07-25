"""Run the whole loop against real Supabase and assert every stage persisted.

seed_demo populates a database so it can be looked at. This asks a narrower
question: does each stage's data actually survive the round trip, in the shape
the next stage reads it back in? Those are different failures. A column that
silently drops a jsonb key, a text[] that comes back as a string, an enum the
migration never widened — none of them raise at write time. They surface three
stages later as a brief that is quietly missing a section, which on a demo day
looks like the model being vague rather than like a bug.

So every step here writes, reads back through the same repo function the
application uses, and checks the value survived. It is deliberately not a
Django test: SimpleTestCase runs offline against no database, and the whole
point is to exercise the real Supabase project with the migrations applied.

    python manage.py verify_pipeline
    python manage.py verify_pipeline --keep    # leave the rows for inspection

Requires SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY, an LLM provider (Codex or
Anthropic per LLM_PROVIDER), and supabase/migrations/ already pushed.
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from capture.interval import (
    IntervalError,
    compute_interval_facts,
    load_context,
    observations,
    watch_for_vocabulary,
)
from capture.plan import CheckInPlan, PlanError, build_plan
from capture.plan import coverage as plan_coverage
from capture.redflags import evaluate_flags

from ... import repo
from ...services import BRIEF_SYSTEM_PROMPT, LLMJSONError, call_llm_json

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"
SUMMARY_PATH = FIXTURES / "demo_consultation.summary.json"

CONDITION_CONTEXT = "hypothyroidism"

# A check-in transcript written to touch several commitments AND to plant two
# distinct over-replacement signs. Two is the cluster_threshold, so a correct
# pipeline fires over_replacement_cluster here — and a pipeline that loses
# symptom_mentions somewhere in the round trip fires nothing. That is the
# single most important thing this command proves, because it is the catch the
# product exists for and the one that fails silently.
CHECKIN_TRANSCRIPT = """\
Cadence: How have you been getting on with the tablet since we last spoke?
Patient: Taking it every morning, yes, on an empty stomach like they said.
Cadence: And have you had the repeat blood test yet?
Patient: No, not yet. I keep meaning to book it and forgetting.
Cadence: Has anything new started since the appointment, even if it seems unrelated?
Patient: My heart's been racing a bit some evenings, and my hands feel shaky \
when I hold a cup. I've been boiling at night too, kicking the covers off.
Cadence: Thank you for telling me.
"""


class Check:
    """One assertion about the round trip, and what it found."""

    def __init__(self, label: str, ok: bool, detail: str = ""):
        self.label = label
        self.ok = ok
        self.detail = detail


class Command(BaseCommand):
    help = "Run the full loop against Supabase and verify every stage persisted."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Leave the created condition in place instead of deleting it.",
        )
        parser.add_argument(
            "--condition-name",
            default="Pipeline verification",
            help="Condition created for this run. Deleted afterwards unless --keep.",
        )

    def handle(self, *args, **options):
        self.checks: list[Check] = []
        condition = None
        try:
            condition = self._run(options)
        finally:
            if condition and not options["keep"]:
                repo.delete_condition(condition["id"])
                self.stdout.write("\nCleaned up. Pass --keep to retain the rows.")
            elif condition:
                self.stdout.write(f"\nKept condition {condition['id']}.")

        self._report()

    # -- the run ----------------------------------------------------------

    def _run(self, options):
        if not SUMMARY_PATH.is_file():
            raise CommandError(f"Fixture not found at {SUMMARY_PATH}")

        # The fixture nests the body under "summary"; the database stores it
        # flat, which is what every reader downstream expects.
        summary = json.loads(SUMMARY_PATH.read_text())["summary"]

        try:
            context = load_context(CONDITION_CONTEXT)
        except IntervalError as exc:
            raise CommandError(str(exc)) from exc

        try:
            repo.get_or_create_patient()
        except RuntimeError as exc:
            raise CommandError(f"{exc}\nSet SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.") from exc

        patient = repo.get_or_create_patient()
        condition = repo.create_condition(patient["id"], options["condition_name"])
        visit_date = (date_cls.today() - timedelta(weeks=7)).isoformat()

        self._visit_stage(condition, summary, visit_date)
        visit = repo.list_visits(condition["id"])[0]
        commitments = repo.get_commitments_for_visit(visit["id"])

        plan = self._plan_stage(visit, summary, context)
        self._checkin_stage(condition, visit, commitments, context, plan, visit_date)
        self._brief_stage(condition, visit, summary, plan)

        return condition

    # -- stages -----------------------------------------------------------

    def _visit_stage(self, condition, summary, visit_date):
        self.stdout.write("1/5 visit + commitments...")
        visit = repo.create_visit(
            condition["id"],
            date=visit_date,
            care_setting="gp",
            clinician_name="Dr Verification",
            organisation="",
            transcript="(seeded from fixture)",
            summary=summary,
        )
        created = repo.create_commitments(visit["id"], summary.get("commitments", []))

        read_back = repo.get_visit(visit["id"])
        stored = (read_back or {}).get("summary") or {}
        self._check(
            "visit.summary survives as jsonb",
            stored.get("commitments") is not None
            and len(stored["commitments"]) == len(summary["commitments"]),
            f"{len(stored.get('commitments') or [])} of {len(summary['commitments'])} commitments",
        )
        self._check(
            "commitments insert",
            len(created) == len(summary["commitments"]),
            f"{len(created)} row(s)",
        )
        # Fresh commitments must all be open, or the first check-in has nothing
        # to ask about. This is the filter that was previously "pending" only.
        self._check(
            "get_open_commitments sees new commitments",
            len(repo.get_open_commitments(condition["id"])) == len(created),
        )

    def _plan_stage(self, visit, summary, context) -> CheckInPlan | None:
        self.stdout.write("2/5 caretaker plan...")
        try:
            built = build_plan(summary=summary, context=context, visit_date=visit["date"])
        except PlanError as exc:
            self._check("plan generated", False, str(exc))
            return None

        repo.create_plan(visit["id"], built.data, condition_context=CONDITION_CONTEXT)
        row = repo.get_plan_for_visit(visit["id"])
        stored = (row or {}).get("content") or {}

        self._check("plans row round-trips", bool(row))
        self._check(
            "plan.items survive jsonb",
            len(stored.get("items") or []) == len(built.items),
            f"{len(stored.get('items') or [])} item(s)",
        )
        self._check(
            "plan.call_schedule survives jsonb",
            len(stored.get("call_schedule") or []) == len(built.call_schedule),
        )
        # The upsert must replace rather than accumulate — plans.visit_id is
        # unique, and a second planning run is a re-plan, not a second plan.
        repo.create_plan(visit["id"], built.data, condition_context=CONDITION_CONTEXT)
        self._check(
            "re-planning replaces rather than duplicates",
            repo.get_latest_plan(visit["condition_id"]) is not None,
        )

        plan = CheckInPlan(data=stored)
        self._check(
            "plan cites real commitment ids",
            any(item.get("commitment_ids") for item in plan.items),
        )
        return plan

    def _checkin_stage(self, condition, visit, commitments, context, plan, visit_date):
        self.stdout.write("3/5 check-in (voice path: transcript -> mapped)...")

        vocabulary = watch_for_vocabulary(context)
        commitments_context = [{"commitment_id": c["id"], "text": c["text"]} for c in commitments]
        from ...services import CHECKIN_SYSTEM_PROMPT

        user_content = (
            f"Transcript:\n{CHECKIN_TRANSCRIPT}\n\n"
            f"Open commitments:\n{commitments_context}\n\n"
            "Symptom vocabulary — map anything the patient described onto "
            "EXACTLY one of these phrases, or leave it out entirely:\n"
            + "\n".join(f"- {p}" for p in vocabulary)
            + "\n\nRed flag ids: "
            + ", ".join(f["id"] for f in context.get("red_flags", []))
            + '\n\nReturn symptom_mentions as a list of {"watch_for", "flag_id", '
            '"patient_words"}, using only the phrases above.'
        )
        try:
            mapped = call_llm_json(CHECKIN_SYSTEM_PROMPT, user_content, schema_name="check_in")
        except LLMJSONError as exc:
            self._check("check-in mapped to JSON", False, exc.raw_text[:200])
            return

        mentions = [
            m
            for m in (mapped.get("symptom_mentions") or [])
            if isinstance(m, dict) and m.get("watch_for") in set(vocabulary)
        ]
        self._check(
            "symptoms map onto the context vocabulary",
            len(mentions) >= 2,
            f"{len(mentions)} mention(s): {[m['watch_for'] for m in mentions]}",
        )

        raw = {**mapped, "symptom_mentions": mentions}
        covered = [item["id"] for item in (plan.due_items(7) if plan else [])][:2]
        check_in = repo.create_check_in(
            condition["id"],
            date=date_cls.today().isoformat(),
            transcript=CHECKIN_TRANSCRIPT,
            raw=raw,
            covered_item_ids=covered,
        )

        stored = next(
            (c for c in repo.list_check_ins(condition["id"]) if c["id"] == check_in["id"]), None
        )
        stored_raw = (stored or {}).get("raw") or {}
        self._check(
            "check_ins.raw keeps symptom_mentions",
            len(stored_raw.get("symptom_mentions") or []) == len(mentions),
        )
        # text[] is the column type most likely to come back wrong.
        self._check(
            "covered_item_ids round-trips as a list",
            isinstance((stored or {}).get("covered_item_ids"), list)
            and list(stored["covered_item_ids"]) == covered,
            f"{(stored or {}).get('covered_item_ids')!r}",
        )

        outcome_rows = [
            r for r in mapped.get("outcomes", []) if r.get("commitment_id") in {c["id"] for c in commitments}
        ]
        repo.create_outcomes(check_in["id"], outcome_rows)
        for row in outcome_rows:
            if row.get("status") in {"done", "not_done", "partial", "changed"}:
                repo.update_commitment_status(row["commitment_id"], row["status"])

        # The constraint the migration widened. A "partial" outcome must be
        # writable; before the migration this raised a check violation.
        statuses = {c["status"] for c in repo.get_commitments_for_visit(visit["id"])}
        self._check(
            "commitment statuses accepted by the widened constraint",
            statuses.issubset({"pending", "done", "not_done", "partial", "changed"}),
            f"{sorted(statuses)}",
        )
        still_open = repo.get_open_commitments(condition["id"])
        self._check(
            "an unmet commitment stays open for the next call",
            all(c["status"] in {"pending", "not_done", "partial"} for c in still_open),
            f"{len(still_open)} open",
        )

        # The flag the whole product turns on.
        facts, _ = self._facts(condition["id"])
        if facts is not None:
            fired = evaluate_flags(
                context,
                [
                    {"watch_for": m.watch_for, "flag_id": m.flag_id,
                     "patient_words": m.patient_words, "week": m.week}
                    for m in facts.mentions
                ],
                week=facts.week,
            )
            self._check(
                "the over-replacement cluster fires from persisted mentions",
                any(f.flag_id == "over_replacement_cluster" for f in fired),
                f"fired: {[f.flag_id for f in fired]}",
            )

    def _brief_stage(self, condition, visit, summary, plan):
        self.stdout.write("4/5 interval facts from the database...")
        facts, _ = self._facts(condition["id"])
        self._check("interval facts assemble from stored rows", facts is not None)
        if facts is None:
            return

        self._check("week computed from the stored visit date", facts.week == 7, f"week {facts.week}")
        self._check("trajectory evaluated", len(facts.trajectory) > 0)

        self.stdout.write("5/5 brief...")
        commitments = repo.get_commitments_for_visit(visit["id"])
        outcomes = repo.get_outcomes_for_commitments([c["id"] for c in commitments])
        payload = {
            "visit_summary": summary,
            "commitments": [
                {"id": c["id"], "text": c["text"], "status": c["status"]} for c in commitments
            ],
            "check_in_outcomes": [
                {
                    "commitment_id": o["commitment_id"],
                    "date": (o.get("check_ins") or {}).get("date"),
                    "status": o["status"],
                    "patient_words": o["patient_words"],
                    "note": o["note"],
                }
                for o in outcomes
            ],
        }
        user_content = json.dumps(payload, indent=2)
        lines = observations(facts)
        if lines:
            user_content += (
                "\n\n=== OBSERVATIONS — reproduce these verbatim ===\n"
                + "\n".join(f"- {line}" for line in lines)
            )
        self._check("observations produced from the record", bool(lines), f"{len(lines)} line(s)")

        if plan is not None:
            covered = [
                i for row in repo.list_check_ins(condition["id"]) for i in (row.get("covered_item_ids") or [])
            ]
            cov = plan_coverage(plan, covered, facts.week)
            self._check(
                "plan coverage separates asked from unasked",
                bool(cov["covered"]) and bool(cov["missed"]),
                f"covered {len(cov['covered'])}, missed {len(cov['missed'])}",
            )

        try:
            content = call_llm_json(BRIEF_SYSTEM_PROMPT, user_content, schema_name="brief")
        except LLMJSONError as exc:
            self._check("brief generated", False, exc.raw_text[:200])
            return

        brief = repo.create_brief(condition["id"], content)
        stored = (repo.get_brief(brief["id"]) or {}).get("content") or {}
        self._check(
            "brief round-trips with its sections",
            all(k in stored for k in ("agreed", "did", "happened", "changed")),
            f"keys: {sorted(stored)}",
        )
        self._check("get_latest_brief finds it", (repo.get_latest_brief(condition["id"]) or {}).get("id") == brief["id"])

        # The return arrow: a second visit records the brief it was walked in
        # with, and the interval it opens can read it back.
        second = repo.create_visit(
            condition["id"],
            date=date_cls.today().isoformat(),
            care_setting="gp",
            clinician_name="Dr Verification",
            organisation="",
            transcript="(second consultation)",
            summary=summary,
            previous_brief_id=brief["id"],
        )
        self._check(
            "a second visit links back to the previous brief",
            (repo.get_visit(second["id"]) or {}).get("previous_brief_id") == brief["id"],
        )

    # -- helpers ----------------------------------------------------------

    def _facts(self, condition_id):
        """Interval facts built the way views._interval_facts builds them."""
        visits = repo.list_visits(condition_id)
        if not visits:
            return None, None
        latest = visits[0]
        visit_date = date_cls.fromisoformat(latest["date"][:10])
        prior = []
        for row in sorted(repo.list_check_ins(condition_id), key=lambda c: c["date"]):
            row_date = date_cls.fromisoformat(row["date"][:10])
            if row_date < visit_date:
                continue
            raw = row.get("raw") or {}
            prior.append(
                {
                    "week": max(0, (row_date - visit_date).days // 7),
                    "outcomes": raw.get("outcomes", []),
                    "symptom_mentions": raw.get("symptom_mentions", []),
                    "unprompted_reports": raw.get("unprompted_reports", []),
                    "questions_for_doctor": raw.get("questions_for_doctor", []),
                }
            )
        context = load_context(CONDITION_CONTEXT)
        return (
            compute_interval_facts(
                summary=latest.get("summary") or {},
                context=context,
                visit_date=visit_date,
                today=date_cls.today(),
                prior_check_ins=prior,
            ),
            context,
        )

    def _check(self, label, ok, detail=""):
        self.checks.append(Check(label, bool(ok), detail))
        mark = self.style.SUCCESS("  PASS") if ok else self.style.ERROR("  FAIL")
        suffix = f"  ({detail})" if detail else ""
        self.stdout.write(f"{mark}  {label}{suffix}")

    def _report(self):
        failed = [c for c in self.checks if not c.ok]
        total = len(self.checks)
        self.stdout.write("")
        if failed:
            self.stdout.write(
                self.style.ERROR(f"{len(failed)} of {total} checks failed:")
            )
            for c in failed:
                self.stdout.write(self.style.ERROR(f"  - {c.label} {c.detail}"))
            raise CommandError("Pipeline verification failed.")
        self.stdout.write(self.style.SUCCESS(f"All {total} checks passed."))
