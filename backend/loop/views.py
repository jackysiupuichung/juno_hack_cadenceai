"""API endpoints for the loop: timeline, visit summarisation, check-ins, and
the next-visit brief. See product_doc.md for the screens these serve."""

from __future__ import annotations

from datetime import date as date_cls

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import repo
from .services import (
    BRIEF_SYSTEM_PROMPT,
    CHECKIN_SYSTEM_PROMPT,
    SUMMARISE_SYSTEM_PROMPT,
    LLMJSONError,
    call_claude_json,
)

RESOLVED_STATUSES = {"done", "not_done", "changed"}


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
        summary = call_claude_json(SUMMARISE_SYSTEM_PROMPT, transcript)
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
            mapped = call_claude_json(CHECKIN_SYSTEM_PROMPT, user_content)
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

    return Response({**check_in, "outcomes": outcomes}, status=status.HTTP_201_CREATED)


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

    try:
        content = call_claude_json(BRIEF_SYSTEM_PROMPT, str(payload))
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
