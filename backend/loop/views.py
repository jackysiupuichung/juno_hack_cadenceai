"""API endpoints for the loop: timeline, visit summarisation, check-ins, and
the next-visit brief. See product_doc.md for the screens these serve."""

from __future__ import annotations

import json
from datetime import date as date_cls

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from capture.interval import (
    IntervalError,
    as_agent_brief,
    compute_interval_facts,
    load_context,
    observations,
)
from capture.redflags import evaluate_flags

from . import repo
from .services import (
    BRIEF_SYSTEM_PROMPT,
    CHECKIN_SYSTEM_PROMPT,
    SUMMARISE_SYSTEM_PROMPT,
    LLMJSONError,
    call_claude_json,
)

RESOLVED_STATUSES = {"done", "not_done", "changed"}

# One condition for the demo; the context file is matched by this id. Widening
# this means matching a visit's diagnosis to a context file, which is a real
# design question and not one a single-condition demo needs to answer.
CONDITION_CONTEXT = "hypothyroidism"


def _interval_facts(condition_id: str):
    """The interval as of today, assembled from what Supabase holds.

    Returns (facts, context, check_ins) or (None, None, []) when there is no
    visit yet — the loop cannot describe an interval that has not opened.
    """
    visits = repo.list_visits(condition_id)
    if not visits:
        return None, None, []

    latest = visits[0]
    check_ins = repo.list_check_ins(condition_id)
    context = load_context(CONDITION_CONTEXT)

    visit_date = date_cls.fromisoformat(latest["date"][:10])
    prior = []
    for row in sorted(check_ins, key=lambda c: c["date"]):
        raw = row.get("raw") or {}
        prior.append(
            {
                "week": max(0, (date_cls.fromisoformat(row["date"][:10]) - visit_date).days // 7),
                "outcomes": raw.get("outcomes", []),
                "symptom_mentions": raw.get("symptom_mentions", []),
                "unprompted_reports": raw.get("unprompted_reports", []),
                "questions_for_doctor": raw.get("questions_for_doctor", []),
            }
        )

    facts = compute_interval_facts(
        summary=latest.get("summary") or {},
        context=context,
        visit_date=visit_date,
        today=date_cls.today(),
        prior_check_ins=prior,
    )
    return facts, context, prior


@api_view(["GET"])
def timeline(request):
    """Home screen: the open-commitments panel + a merged, newest-first feed
    of visits, check-ins, and briefs."""
    condition = repo.get_default_condition()
    condition_id = condition["id"]

    visits = repo.list_visits(condition_id)
    check_ins = repo.list_check_ins(condition_id)
    briefs = repo.list_briefs(condition_id)

    events = []
    for v in visits:
        events.append(
            {
                "kind": "visit",
                "date": v["date"],
                "id": v["id"],
                "care_setting": v["care_setting"],
                "diagnosis_preview": (v.get("summary") or {}).get("doctor_diagnosis", ""),
            }
        )
    for c in check_ins:
        outcomes = c.get("outcomes") or []
        preview = (outcomes[0].get("note") or outcomes[0].get("patient_words")) if outcomes else ""
        events.append({"kind": "check_in", "date": c["date"], "id": c["id"], "preview": preview})
    for b in briefs:
        events.append(
            {"kind": "brief", "date": b["generated_at"][:10], "id": b["id"]}
        )
    events.sort(key=lambda e: e["date"], reverse=True)

    return Response(
        {
            "condition": {"id": condition_id, "name": condition["name"]},
            "open_commitments": repo.get_open_commitments(condition_id),
            "events": events,
            "has_visits": len(visits) > 0,
        }
    )


@api_view(["POST"])
def summarise(request):
    """
    Transcript (pasted, or the output of /api/transcribe) in; a persisted
    visit + its Claude-structured summary + extracted commitments out.
    """
    transcript = (request.data.get("transcript") or "").strip()
    if not transcript:
        return Response({"error": "transcript is required"}, status=status.HTTP_400_BAD_REQUEST)

    condition = repo.get_default_condition()

    try:
        summary = call_claude_json(
            SUMMARISE_SYSTEM_PROMPT, transcript, schema_name="visit_summary"
        )
    except LLMJSONError as exc:
        return Response(
            {"error": "Claude did not return valid JSON", "raw": exc.raw_text},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    visit = repo.create_visit(
        condition["id"],
        date=request.data.get("date") or date_cls.today().isoformat(),
        care_setting=request.data.get("care_setting", "gp"),
        clinician_name=request.data.get("clinician_name", ""),
        organisation=request.data.get("organisation", ""),
        transcript=transcript,
        summary=summary,
    )
    commitments = repo.create_commitments(visit["id"], summary.get("commitments", []))

    return Response({**visit, "commitments": commitments}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def checkin_context(request):
    """What the voice agent needs to know before it dials.

    The ElevenLabs agent is configured with the standing instructions; this
    supplies the two things that change per call — the facts of this interval,
    and the clinical context to reason over. Fetched at call time rather than
    baked into the agent so a check-in always reflects what the record holds
    now, including anything an earlier call in the same interval turned up.
    """
    condition = repo.get_default_condition()
    try:
        facts, context, _ = _interval_facts(condition["id"])
    except IntervalError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if facts is None:
        return Response(
            {"error": "no visits recorded yet"}, status=status.HTTP_400_BAD_REQUEST
        )

    return Response(
        {
            "week": facts.week,
            "visit_date": facts.visit_date.isoformat(),
            "is_first_check_in": facts.is_first_check_in,
            "interval_brief": as_agent_brief(facts),
            "disease_context": context,
            "open_commitments": [
                {
                    "commitment_id": c.commitment_id,
                    "text": c.text,
                    "type": c.type,
                    "status": c.status,
                }
                for c in facts.open_commitments
            ],
            "already_reported": [
                {"watch_for": m.watch_for, "week": m.week}
                for m in facts.mentions
            ],
        }
    )


@api_view(["POST"])
def checkin(request):
    """
    Voice path:        { "transcript": "..." }  -> mapped onto open commitments via Claude
    Text-form fallback: { "outcomes": [{"commitment_id": "...", "status": "...", "note": "..."}] }
    """
    condition = repo.get_default_condition()
    open_commitments = repo.get_open_commitments(condition["id"])
    transcript = request.data.get("transcript", "")

    if transcript:
        commitments_context = [{"commitment_id": c["id"], "text": c["text"]} for c in open_commitments]
        user_content = f"Transcript:\n{transcript}\n\nOpen commitments:\n{commitments_context}"
        try:
            mapped = call_claude_json(
                CHECKIN_SYSTEM_PROMPT, user_content, schema_name="check_in"
            )
        except LLMJSONError as exc:
            return Response(
                {"error": "Claude did not return valid JSON", "raw": exc.raw_text},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        outcome_rows = mapped.get("outcomes", [])
        raw = mapped
    else:
        outcome_rows = request.data.get("outcomes", [])
        raw = {"outcomes": outcome_rows}

    # Symptom mentions are not part of check_in.schema.json, but they must be
    # stored: the over-replacement cluster assembles one symptom at a time
    # across calls weeks apart, so a mention dropped here is a flag that never
    # fires. The voice agent supplies them already mapped to the context's
    # vocabulary; a text-form check-in has none.
    raw["symptom_mentions"] = request.data.get("symptom_mentions", [])

    check_in = repo.create_check_in(
        condition["id"],
        date=request.data.get("date") or date_cls.today().isoformat(),
        transcript=transcript,
        raw=raw,
    )

    valid_ids = {c["id"] for c in open_commitments}
    outcome_rows = [row for row in outcome_rows if row.get("commitment_id") in valid_ids]
    outcomes = repo.create_outcomes(check_in["id"], outcome_rows)

    for row in outcome_rows:
        if row.get("status") in RESOLVED_STATUSES:
            repo.update_commitment_status(row["commitment_id"], row["status"])

    # Evaluate red flags over everything reported this INTERVAL, not just this
    # call. The cluster that matters most in this condition assembles one
    # symptom at a time across calls weeks apart, and is invisible to anything
    # looking at a single transcript.
    fired = []
    try:
        facts, context, prior = _interval_facts(condition["id"])
        if facts is not None:
            mentions = [
                {
                    "watch_for": m.watch_for,
                    "flag_id": m.flag_id,
                    "patient_words": m.patient_words,
                    "week": m.week,
                }
                for m in facts.mentions
            ] + [
                {**m, "week": facts.week}
                for m in (raw.get("symptom_mentions") or [])
            ]
            fired = [
                {
                    "flag_id": f.flag_id,
                    "urgency": f.urgency,
                    "matched": f.matched,
                    # Verbatim from the cited context file — never composed.
                    "patient_facing": f.patient_facing,
                    "action": f.action,
                    "first_seen_week": f.first_seen_week,
                }
                for f in evaluate_flags(context, mentions, week=facts.week)
            ]
    except IntervalError:
        # No disease context for this condition: the check-in is still a valid
        # record, it just carries no flag evaluation.
        fired = []

    return Response(
        {**check_in, "outcomes": outcomes, "red_flags": fired},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def brief(request):
    """Generate the next-visit brief from the latest visit + every check-in
    outcome recorded since. The hero screen — see product_doc.md."""
    condition = repo.get_default_condition()
    visits = repo.list_visits(condition["id"])
    if not visits:
        return Response({"error": "no visits recorded yet"}, status=status.HTTP_400_BAD_REQUEST)

    latest_visit = visits[0]
    commitments = repo.get_commitments_for_visit(latest_visit["id"])
    outcomes = repo.get_outcomes_for_commitments([c["id"] for c in commitments])

    payload = {
        "visit_summary": latest_visit.get("summary"),
        "commitments": [{"id": c["id"], "text": c["text"], "status": c["status"]} for c in commitments],
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

    # Anything that measures this interval against the guideline is written in
    # Python and handed over as a line to reproduce verbatim. "The repeat blood
    # test was due around week 7 and is 3 weeks past" is a fact about the
    # record; "the dose may be too high" is a diagnosis. Pre-writing the
    # factual form denies the model the chance to produce the second kind.
    user_content = json.dumps(payload, indent=2)
    try:
        facts, _, _ = _interval_facts(condition["id"])
        if facts is not None:
            lines = observations(facts)
            if lines:
                user_content += (
                    "\n\n=== OBSERVATIONS — reproduce these verbatim, do not "
                    "reword or extend them ===\n"
                    + "\n".join(f"- {line}" for line in lines)
                )
    except IntervalError:
        pass

    try:
        content = call_claude_json(
            BRIEF_SYSTEM_PROMPT, user_content, schema_name="brief"
        )
    except LLMJSONError as exc:
        return Response(
            {"error": "Claude did not return valid JSON", "raw": exc.raw_text},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    created = repo.create_brief(condition["id"], content)
    return Response(created, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def reset(request):
    """The 'Delete everything' consent control. Cascades via FK constraints."""
    repo.delete_patient_cascade(settings.PATIENT_ID)
    return Response(status=status.HTTP_204_NO_CONTENT)
