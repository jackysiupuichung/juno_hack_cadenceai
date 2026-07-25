"""API endpoints for the loop: patient profile, conditions, timeline, visit
summarisation, check-ins, and the next-visit brief. See product_doc.md for
the screens these serve."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date as date_cls
from datetime import timedelta

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from capture import caretaker
from capture import events as ev
from capture import medication
from capture import safety
from capture.interval import (
    IntervalError,
    as_agent_brief,
    compute_interval_facts,
    load_context,
    observations,
    watch_for_vocabulary,
)
from capture.plan import CheckInPlan, PlanError, build_plan
from capture.plan import as_agent_brief as plan_as_agent_brief
from capture.plan import coverage as plan_coverage
from capture.redflags import evaluate_flags

from . import caretaker_repo, medication_repo, repo
from .services import (
    BRIEF_SYSTEM_PROMPT,
    CHECKIN_SYSTEM_PROMPT,
    EVENTS_SYSTEM_PROMPT,
    QA_SYSTEM_PROMPT,
    SUMMARISE_SYSTEM_PROMPT,
    LLMJSONError,
    call_llm_json,
)

# A commitment leaves "pending" once a check-in actually settles it. "partial"
# now belongs here: the patient took four of the seven days, which is a real
# answer and one the brief must report. It was previously filtered out, so the
# commitment sat at "pending" as though nobody had ever asked.
RESOLVED_STATUSES = {"done", "not_done", "partial", "changed"}

# One condition for the demo; the context file is matched by this id. Widening
# this means matching a visit's diagnosis to a context file, which is a real
# design question and not one a single-condition demo needs to answer.
CONDITION_CONTEXT = "hypothyroidism"


def _interval_facts(condition_id: str):
    """The interval as of today, assembled from what Supabase holds.

    Returns (facts, context, check_ins) or (None, None, []) when there is no
    visit yet — the loop cannot describe an interval that has not opened.

    The interval belongs to the latest visit, but the record does not start
    there. A patient on their third appointment has a history, and a check-in
    that opens as though they had none is exactly the cold start Cadence
    exists to end — so the brief that closed the previous interval, and the
    dates of the visits before this one, are carried in alongside.
    """
    visits = repo.list_visits(condition_id)
    if not visits:
        return None, None, []

    latest = visits[0]
    check_ins = repo.list_check_ins(condition_id)
    context = load_context(CONDITION_CONTEXT)

    visit_date = date_cls.fromisoformat(latest["date"][:10])

    # Check-ins belong to the condition, not to a visit, so on a second
    # interval the table still holds the previous one's calls. Only those
    # after this visit describe this interval; the rest are history the
    # previous brief already accounts for.
    prior = []
    for row in sorted(check_ins, key=lambda c: c["date"]):
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

    previous_brief = None
    if latest.get("previous_brief_id"):
        brief_row = repo.get_brief(latest["previous_brief_id"])
        previous_brief = (brief_row or {}).get("content")

    # The stored summary jsonb is the visit as Claude extracted it; it carries
    # no status, because status is what the interval since has established.
    # Overlay the commitment rows, which do — otherwise every commitment reads
    # as "unknown" no matter what the patient has since answered.
    summary = dict(latest.get("summary") or {})
    rows = repo.get_commitments_for_visit(latest["id"])
    if rows:
        summary["commitments"] = [
            {
                "id": row["id"],
                "text": row.get("text", ""),
                "type": row.get("type", ""),
                "timeframe": row.get("timeframe", ""),
                "source_quote": row.get("source_quote", ""),
                "status": row.get("status", "pending"),
            }
            for row in rows
        ]

    facts = compute_interval_facts(
        summary=summary,
        context=context,
        visit_date=visit_date,
        today=date_cls.today(),
        prior_check_ins=prior,
        previous_brief=previous_brief,
        prior_visit_dates=[date_cls.fromisoformat(v["date"][:10]) for v in visits[1:]],
    )
    return facts, context, prior


def _extract_events(transcript: str, *, on: date_cls, source: str, **links) -> list[dict]:
    """Dated events from a transcript, ready to insert.

    Returns [] on any failure. Event extraction is an enrichment: a visit whose
    chronology could not be parsed is still a visit, and losing the summary
    because the dating call failed would trade the record for a detail. The
    conversation date goes in explicitly because every relative timing the
    patient gives — "a fortnight ago" — is resolved against it.
    """
    if not transcript.strip():
        return []

    user_content = (
        f"Conversation date: {on.isoformat()}\n\n"
        f"Transcript:\n{transcript}"
    )
    try:
        extracted = call_llm_json(EVENTS_SYSTEM_PROMPT, user_content, schema_name="event")
    except LLMJSONError:
        return []

    rows = []
    for item in extracted.get("events", []):
        event = ev.from_extraction(item, conversation_date=on, source=source)
        if event is not None:
            rows.append(ev.to_row(event, **links))
    return rows


def _resolve_scheduled(condition_id: str, created: list[dict]) -> None:
    """Close out a due date when the thing it was waiting for actually happens.

    Matching is by kind alone, taking the oldest outstanding due date of that
    kind. That is deliberately loose: the alternative is asking a model whether
    "the blood test I had last Tuesday" is the same test the guideline
    scheduled for week 7, and a wrong answer there either hides a genuinely
    overdue test or reports one that was done. Loose matching fails toward
    marking things done, so the counterpart is that `overdue` is only ever
    computed from what remains — an unmatched event never invents a new gap.
    """
    done_kinds = {
        row["kind"] for row in created if row.get("occurred_at") and row.get("kind")
    }
    if not done_kinds:
        return

    outstanding = [
        row
        for row in repo.list_events(condition_id)
        if row.get("due_at") and not row.get("occurred_at") and not row.get("fulfilled_by")
    ]
    outstanding.sort(key=lambda r: r["due_at"])

    for row in created:
        if not row.get("occurred_at"):
            continue
        match = next(
            (o for o in outstanding if o["kind"] == row["kind"]), None
        )
        if match and row.get("id"):
            repo.mark_event_fulfilled(match["id"], row["id"])
            outstanding.remove(match)


def _load_plan(condition_id: str) -> CheckInPlan | None:
    """The caretaker's agenda for the current interval, if one was made.

    Returns None rather than raising when there is no plan: visits recorded
    before planning existed, and visits whose planning call failed, must still
    be able to run a check-in. The agent falls back to reasoning from the
    disease context alone, which is what it did before plans existed.
    """
    row = repo.get_latest_plan(condition_id)
    return CheckInPlan(data=row["content"]) if row else None


def _condition_or_404(condition_id: str):
    condition = repo.get_condition(condition_id) if condition_id else None
    if not condition:
        return None, Response({"error": "condition not found"}, status=status.HTTP_404_NOT_FOUND)
    return condition, None


# --- Patient profile ---------------------------------------------------------


@api_view(["GET", "PATCH"])
def patient(request):
    """GET returns the (single, hardcoded) patient's profile. PATCH updates
    their name — set during onboarding."""
    if request.method == "PATCH":
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        p = repo.get_or_create_patient()
        updated = repo.update_patient_name(p["id"], name)
        return Response(updated)

    return Response(repo.get_or_create_patient())


# --- The caretaker's standing context ----------------------------------------


# Only these may be written from the client. The list is explicit rather than
# "whatever was sent" because this row is upserted whole: an unlisted key would
# be a silent no-op at best, and at worst the shape the database rejects
# mid-call. Notably absent is anything clinical — this table holds
# circumstances, and a clinical field arriving here would be a design error
# worth failing on rather than storing.
CARETAKER_FIELDS = (
    "preferred_name",
    "contact_window",
    "call_length_preference",
    "living_situation",
    "access_needs",
    "medication_barriers",
    "priorities",
    "supporter_name",
    "supporter_relationship",
    "supporter_may_be_contacted",
    "notes",
)


@api_view(["GET", "PUT"])
def caretaker_context(request):
    """What the caretaker knows about the person before it rings.

    GET always returns a context, empty for a patient nothing is known about —
    the client renders a blank form either way, and a 404 would make it handle
    two representations of the same thing.

    PUT merges rather than replaces. The client edits one field at a time, and a
    replace would mean every partial save silently cleared everything the
    patient had told us on a previous screen.
    """
    p = repo.get_or_create_patient()
    current = caretaker_repo.get_caretaker_context(p["id"])

    if request.method == "GET":
        return Response(caretaker.to_row(current, p["id"]))

    updates = {k: v for k, v in request.data.items() if k in CARETAKER_FIELDS}
    unknown = [k for k in request.data if k not in CARETAKER_FIELDS]
    if unknown:
        return Response(
            {"error": f"unknown fields: {', '.join(sorted(unknown))}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    preference = updates.get("call_length_preference")
    if preference is not None and preference not in caretaker.CALL_LENGTH_ITEMS:
        return Response(
            {
                "error": "call_length_preference must be one of "
                + ", ".join(caretaker.CALL_LENGTH_ITEMS)
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    merged = replace(current, **updates)
    return Response(caretaker_repo.save_caretaker_context(p["id"], merged))


# --- The medication thread ---------------------------------------------------


@api_view(["GET"])
def medications(request):
    """The medication thread for a condition, as the calls have left it.

    Returns the stored rows plus what the thread still needs today, so a client
    can show the same outstanding items the next call will raise rather than
    reimplementing the sequencing rules that decide them.
    """
    condition, error = _condition_or_404(request.query_params.get("condition_id"))
    if error:
        return error

    rows = medication_repo.list_medications(condition["id"])
    meds = [medication_repo.from_row(row) for row in rows]

    # Days since the consultation that opened this interval. Without a visit
    # there is no clock, and no medication either, so zero is only ever reached
    # with an empty list.
    visits = repo.list_visits(condition["id"])
    day = (
        medication.days_since(
            date_cls.fromisoformat(visits[-1]["date"][:10]), date_cls.today()
        )
        if visits
        else 0
    )

    return Response(
        {
            "medications": [
                {
                    **row,
                    # Computed, never stored: a gap closes the moment a
                    # confirmed value arrives, and a stored flag would go stale.
                    "gaps": med.gaps,
                    "is_complete": med.is_complete,
                    "needs_label_photo": med.needs_label_photo,
                    "pending_confirmation": med.pending_confirmation,
                    "reminders_ready": med.reminders_ready,
                    "daily_reminder": medication.daily_reminder(med),
                }
                for row, med in zip(rows, meds)
            ],
            "day": day,
            "due_tasks": [
                {
                    "kind": t.kind,
                    "medication": t.medication,
                    "intent": t.intent,
                    "priority": t.priority,
                }
                for t in medication.due_tasks(meds, day=day)
            ],
        }
    )


# --- Conditions ("My Conditions" home) ---------------------------------------


@api_view(["GET", "POST"])
def conditions(request):
    """GET lists every condition with its appointment count and most recent
    follow-up plan (the Home screen's reminder). POST creates a new one."""
    p = repo.get_or_create_patient()

    if request.method == "POST":
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        created = repo.create_condition(p["id"], name)
        return Response(created, status=status.HTTP_201_CREATED)

    result = []
    for c in repo.list_conditions(p["id"]):
        visits = repo.list_visits(c["id"])
        reminder = None
        for v in visits:  # newest first
            plan = (v.get("summary") or {}).get("future_plan") or {}
            if plan.get("follow_up_needed") and plan.get("date_or_timeframe"):
                reminder = {
                    "date_or_timeframe": plan["date_or_timeframe"],
                    "purpose": plan.get("purpose", ""),
                }
                break
        result.append(
            {
                **c,
                "appointment_count": len(visits),
                "reminder": reminder,
            }
        )
    return Response(result)


@api_view(["POST", "DELETE"])
def condition_detail(request, condition_id):
    """POST {"status": "completed" | "active"} updates status.
    DELETE removes the condition and everything under it."""
    condition, error = _condition_or_404(condition_id)
    if error:
        return error

    if request.method == "DELETE":
        repo.delete_condition(condition_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    new_status = request.data.get("status")
    if new_status not in ("active", "completed"):
        return Response(
            {"error": "status must be 'active' or 'completed'"}, status=status.HTTP_400_BAD_REQUEST
        )
    return Response(repo.update_condition_status(condition_id, new_status))


@api_view(["GET", "DELETE"])
def visit_detail(request, visit_id):
    """GET the full visit (summary + transcript + commitments) — the
    Visit detail / summary screen. DELETE removes a single appointment
    (Settings: per-appointment erasure)."""
    if request.method == "DELETE":
        repo.delete_visit(visit_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    visit = repo.get_visit(visit_id)
    if not visit:
        return Response({"error": "visit not found"}, status=status.HTTP_404_NOT_FOUND)
    commitments = repo.get_commitments_for_visit(visit_id)
    return Response({**visit, "commitments": commitments})


@api_view(["POST"])
def ask(request):
    """Chatbot: answer a question about one recorded visit, grounded only in
    its transcript + structured summary. Requires "visit_id" and "question"."""
    visit_id = request.data.get("visit_id")
    question = (request.data.get("question") or "").strip()
    if not visit_id or not question:
        return Response(
            {"error": "visit_id and question are required"}, status=status.HTTP_400_BAD_REQUEST
        )

    visit = repo.get_visit(visit_id)
    if not visit:
        return Response({"error": "visit not found"}, status=status.HTTP_404_NOT_FOUND)

    user_content = (
        f"Transcript:\n{visit.get('transcript', '')}\n\n"
        f"Structured summary:\n{visit.get('summary')}\n\n"
        f"Question: {question}"
    )
    try:
        result = call_llm_json(QA_SYSTEM_PROMPT, user_content)
    except LLMJSONError as exc:
        return Response(
            {"error": "Claude did not return valid JSON", "raw": exc.raw_text},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # The only free-text answer Cadence gives a patient. The prompt forbids
    # advice, but this is the same rope the check-in agent gets and the same
    # backstop applies: a question like "should I take more?" invites exactly
    # the sentence that crosses the line. Fails closed to the fallback, and
    # says so, rather than silently returning something weaker than was asked.
    # This endpoint reads a record back to the patient, so a clinical statement
    # attributed to their clinician is the answer, not a violation — "the
    # doctor said your thyroid levels are low" is what the appointment was.
    # Unattributed clinical claims, and anything recommending a change, are
    # still caught.
    answer = result.get("answer", "")
    if safety.check_utterance(answer, allow_attributed=True):
        result["answer"] = (
            "That one is for your doctor — it is not something I can answer "
            "from this record."
        )
        result["grounded"] = False
        result["withheld"] = True

    return Response(result)


# --- Per-condition timeline / loop -------------------------------------------


@api_view(["GET"])
def timeline(request):
    """Condition detail screen: the open-commitments panel + a merged,
    newest-first feed of visits, check-ins, and briefs for one condition."""
    condition, error = _condition_or_404(request.query_params.get("condition_id"))
    if error:
        return error
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
            "condition": condition,
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
    Requires "condition_id" in the body.
    """
    condition, error = _condition_or_404(request.data.get("condition_id"))
    if error:
        return error

    transcript = (request.data.get("transcript") or "").strip()
    if not transcript:
        return Response({"error": "transcript is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        summary = call_llm_json(
            SUMMARISE_SYSTEM_PROMPT, transcript, schema_name="visit_summary"
        )
    except LLMJSONError as exc:
        return Response(
            {"error": "Claude did not return valid JSON", "raw": exc.raw_text},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # The brief the patient walked in with, if there was one. Recording it is
    # what turns a sequence of visits into a record: this interval knows which
    # interval preceded it, so the next brief can say what carried over rather
    # than starting from the transcript again.
    previous_brief = repo.get_latest_brief(condition["id"])

    visit = repo.create_visit(
        condition["id"],
        date=request.data.get("date") or date_cls.today().isoformat(),
        care_setting=request.data.get("care_setting", "gp"),
        clinician_name=request.data.get("clinician_name", ""),
        organisation=request.data.get("organisation", ""),
        organisation_address=request.data.get("organisation_address", ""),
        transcript=transcript,
        summary=summary,
        previous_brief_id=(previous_brief or {}).get("id"),
    )
    commitments = repo.create_commitments(visit["id"], summary.get("commitments", []))

    # The medication thread, seeded from what the consultation prescribed. Every
    # field is clinician-sourced and confirmed here; the gaps ("a very low
    # dose") are stored as gaps, and closing them is the thread's own work over
    # the following calls. Empty for a consultation that prescribed nothing,
    # which switches the thread off rather than leaving it half-open.
    prescribed = medication_repo.sync_from_summary(
        visit["id"], medication.from_summary(summary)
    )

    # The caretaker plans the interval this visit just opened, while the visit
    # is fresh and nothing is waiting on it. A failure here must not lose the
    # visit — the summary and commitments are the durable artifact, and a
    # check-in can still run unplanned off the disease context alone. The
    # error is reported so the client can offer a re-plan rather than silently
    # running the whole interval without an agenda.
    plan_row, plan_error = None, None
    try:
        context = load_context(CONDITION_CONTEXT)
        built = build_plan(summary=summary, context=context, visit_date=visit["date"])
        plan_row = repo.create_plan(
            visit["id"], built.data, condition_context=CONDITION_CONTEXT
        )
    except (PlanError, IntervalError) as exc:
        plan_error = str(exc)

    # The chronology this visit opens: the visit itself, anything the
    # transcript dated, and the monitoring events the guideline says are now
    # due. The last of those is what a calendar can actually render — a blood
    # test due on a date, rather than "week 7" recomputed on every read.
    visit_date = date_cls.fromisoformat(visit["date"][:10])
    rows = [
        ev.to_row(
            ev.Event(
                kind="visit",
                label=f"Consultation ({visit.get('care_setting', 'gp')})",
                occurred_at=visit_date,
                precision="day",
                source="consultation",
                recorded_at=visit_date,
            ),
            condition_id=condition["id"],
            visit_id=visit["id"],
        )
    ]
    rows += _extract_events(
        transcript,
        on=visit_date,
        source="consultation",
        condition_id=condition["id"],
        visit_id=visit["id"],
    )
    rows += _scheduled_rows(condition["id"], visit["id"], visit_date)

    created_events = repo.create_events(rows) if rows else []

    return Response(
        {
            **visit,
            "commitments": commitments,
            "medications": prescribed,
            "plan": (plan_row or {}).get("content"),
            "plan_error": plan_error,
            "events": created_events,
        },
        status=status.HTTP_201_CREATED,
    )


def _scheduled_rows(condition_id: str, visit_id: str, visit_date: date_cls) -> list[dict]:
    """Due dates the guideline implies, as rows a calendar can render.

    Only events whose clock this visit actually starts. `dose_change` and
    `last_result` hang off things that have not happened yet; when they do, the
    check-in that reports them schedules the follow-up rather than this.
    """
    try:
        context = load_context(CONDITION_CONTEXT)
    except IntervalError:
        return []

    rows = []
    for event in context.get("monitoring", []):
        if event.get("trigger") != "treatment_start":
            continue
        weeks = int(event.get("interval_weeks", 0))
        rows.append(
            ev.to_row(
                ev.Event(
                    kind="test_taken",
                    label=event.get("event", ""),
                    due_at=visit_date + timedelta(weeks=weeks),
                    precision="week",
                    source="scheduled",
                    context_ids=(event.get("id", ""),),
                ),
                condition_id=condition_id,
                visit_id=visit_id,
            )
        )
    return rows


@api_view(["GET"])
def checkin_context(request):
    """What the voice agent needs to know before it dials.

    The ElevenLabs agent is configured with the standing instructions; this
    supplies the two things that change per call — the facts of this interval,
    and the clinical context to reason over. Fetched at call time rather than
    baked into the agent so a check-in always reflects what the record holds
    now, including anything an earlier call in the same interval turned up.
    """
    condition, error = _condition_or_404(request.query_params.get("condition_id"))
    if error:
        return error

    try:
        facts, context, _ = _interval_facts(condition["id"])
    except IntervalError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if facts is None:
        return Response(
            {"error": "no visits recorded yet"}, status=status.HTTP_400_BAD_REQUEST
        )

    plan = _load_plan(condition["id"])

    # The medication thread as the calls have left it, not as the consultation
    # described it. This is the difference between week 6 knowing the tablet was
    # collected on Tuesday and taken at 7:30 every morning, and week 6 opening
    # with "have you collected it yet?" for the sixth time.
    medications = medication_repo.load_medications(condition["id"])
    day = medication.days_since(facts.visit_date, date_cls.today())

    # Who is being rung. Hangs off the patient rather than the condition — it is
    # the same person on every call about every condition they have.
    person = caretaker_repo.get_caretaker_context(settings.PATIENT_ID)

    return Response(
        {
            "week": facts.week,
            "day": day,
            "visit_date": facts.visit_date.isoformat(),
            "is_first_check_in": facts.is_first_check_in,
            "interval_brief": as_agent_brief(facts),
            # Empty when nothing was prescribed, and when nothing is known about
            # the patient. An agent handed an empty section finds something to
            # ask about it, so both are omitted rather than sent blank.
            "medication_brief": medication.as_agent_brief(medications, day=day),
            "caretaker_brief": caretaker.as_agent_brief(person),
            "max_call_items": person.max_call_items,
            # The agenda decided when the visit was summarised, filtered to
            # what is due this week. Empty when the interval was never planned,
            # which the agent handles by reasoning from the context alone.
            "plan_brief": plan_as_agent_brief(plan, facts.week) if plan else "",
            "plan": plan.data if plan else None,
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
def checkin_session(request):
    """Mint a short-lived token so the browser can talk to the voice agent.

    The API key never leaves the server. ElevenLabs issues a conversation
    token scoped to one session; the browser opens the WebRTC connection with
    that, so a leaked token expires rather than granting access to the account.

    Everything that varies per call goes in dynamic_variables rather than into
    the agent's standing configuration, because the agent is configured once
    and this interval changes weekly. The agent's prompt references these by
    name; the clinical reasoning it does is over the same interval brief and
    plan the CLI agent reads, so a voice call and a typed one are the same
    check-in conducted differently.
    """
    condition, error = _condition_or_404(request.data.get("condition_id"))
    if error:
        return error

    agent_id = settings.ELEVENLABS_AGENT_ID
    api_key = settings.ELEVENLABS_API_KEY
    if not agent_id or not api_key:
        # Most people running this repo will not have a voice agent
        # provisioned. Say so precisely enough to act on, and let the client
        # fall back to the form rather than presenting a broken call button.
        return Response(
            {
                "error": "Voice check-in is not configured. Set ELEVENLABS_AGENT_ID "
                "and ELEVENLABS_API_KEY, or use the check-in form."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        facts, context, _ = _interval_facts(condition["id"])
    except IntervalError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if facts is None:
        return Response(
            {"error": "no visits recorded yet"}, status=status.HTTP_400_BAD_REQUEST
        )

    plan = _load_plan(condition["id"])

    try:
        response = requests.get(
            "https://api.elevenlabs.io/v1/convai/conversation/token",
            params={"agent_id": agent_id},
            headers={"xi-api-key": api_key},
            timeout=10,
        )
        response.raise_for_status()
        token = response.json().get("token")
    except requests.RequestException as exc:
        return Response(
            {"error": f"Could not reach ElevenLabs: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not token:
        return Response(
            {"error": "ElevenLabs returned no conversation token"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # The safety boundary travels with the call. The browser agent is outside
    # safety.py's reach — nothing it says passes through the scrubber — so the
    # prohibitions go in as an explicit variable rather than being left to the
    # agent's standing prompt, which is configured elsewhere and can drift.
    prohibited = "\n".join(
        f"- {line}" for line in context.get("safety", {}).get("prohibited_outputs", [])
    )

    return Response(
        {
            "agent_id": agent_id,
            "conversation_token": token,
            "dynamic_variables": {
                "condition_name": facts.condition_name,
                "plain_name": facts.plain_name,
                "week": str(facts.week),
                "is_first_check_in": str(facts.is_first_check_in).lower(),
                "interval_brief": as_agent_brief(facts),
                "plan_brief": plan_as_agent_brief(plan, facts.week) if plan else "",
                "framing_rule": context.get("safety", {}).get("framing_rule", ""),
                "prohibited_outputs": prohibited,
                # The only patient-facing clinical sentences the agent may say,
                # supplied verbatim so it reads one rather than composing its
                # own. Everything else it says about a symptom is prohibited.
                "red_flag_lines": "\n".join(
                    f"- {f.get('id')}: {f.get('patient_facing', '')} {f.get('action', '')}".strip()
                    for f in context.get("red_flags", [])
                ),
            },
            "expires_in": 600,
        }
    )


@api_view(["POST"])
def checkin(request):
    """
    Voice path:        { "condition_id": "...", "transcript": "..." }
    Text-form fallback: { "condition_id": "...", "outcomes": [{"commitment_id": "...", "status": "...", "note": "..."}] }
    """
    condition, error = _condition_or_404(request.data.get("condition_id"))
    if error:
        return error

    open_commitments = repo.get_open_commitments(condition["id"])
    transcript = request.data.get("transcript", "")

    # Symptom mentions are not part of check_in.schema.json, but they must be
    # stored: the over-replacement cluster assembles one symptom at a time
    # across calls weeks apart, so a mention dropped here is a flag that never
    # fires.
    mentions = request.data.get("symptom_mentions", [])
    covered_item_ids = request.data.get("covered_item_ids", [])

    if transcript:
        commitments_context = [{"commitment_id": c["id"], "text": c["text"]} for c in open_commitments]
        user_content = f"Transcript:\n{transcript}\n\nOpen commitments:\n{commitments_context}"

        # A browser voice agent speaks; it does not classify. It cannot map
        # "I've been boiling at night" onto the context's canonical phrase,
        # and a mention that never gets mapped is a red flag that never fires
        # — which is the catch this product exists for. So the mapping happens
        # here, over the transcript, against the same constrained vocabulary
        # the CLI agent is bound to. The enum is what makes the count downstream
        # trustworthy: a phrase the context does not name cannot enter.
        vocabulary, flag_ids = [], []
        try:
            ctx = load_context(CONDITION_CONTEXT)
            vocabulary = watch_for_vocabulary(ctx)
            flag_ids = [f["id"] for f in ctx.get("red_flags", [])]
        except IntervalError:
            pass

        if vocabulary and not mentions:
            user_content += (
                "\n\nSymptom vocabulary — map anything the patient described "
                "onto EXACTLY one of these phrases, or leave it out entirely. "
                "A wrong match is worse than no match:\n"
                + "\n".join(f"- {phrase}" for phrase in vocabulary)
                + "\n\nRed flag ids: " + ", ".join(flag_ids)
                + "\n\nReturn symptom_mentions as a list of "
                '{"watch_for", "flag_id", "patient_words"}, using only the '
                "phrases above."
            )

        try:
            mapped = call_llm_json(
                CHECKIN_SYSTEM_PROMPT, user_content, schema_name="check_in"
            )
        except LLMJSONError as exc:
            return Response(
                {"error": "Claude did not return valid JSON", "raw": exc.raw_text},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        outcome_rows = mapped.get("outcomes", [])
        raw = mapped

        # The schema does not carry symptom_mentions, so anything the model
        # returned arrives outside it and is filtered to the vocabulary here
        # rather than trusted. Explicitly supplied mentions win.
        if not mentions:
            mentions = [
                m
                for m in (mapped.get("symptom_mentions") or [])
                if isinstance(m, dict) and m.get("watch_for") in set(vocabulary)
            ]
    else:
        outcome_rows = request.data.get("outcomes", [])
        raw = {"outcomes": outcome_rows}

    raw["symptom_mentions"] = mentions

    check_in = repo.create_check_in(
        condition["id"],
        date=request.data.get("date") or date_cls.today().isoformat(),
        transcript=transcript,
        raw=raw,
        # Which planned items this call actually reached. Recorded per call
        # because the gap between what was planned and what was asked is
        # itself reportable — a question nobody got to is different from a
        # question answered, and the brief must not conflate them.
        covered_item_ids=covered_item_ids,
    )

    valid_ids = {c["id"] for c in open_commitments}
    outcome_rows = [row for row in outcome_rows if row.get("commitment_id") in valid_ids]
    outcomes = repo.create_outcomes(check_in["id"], outcome_rows)

    # When things happened, as opposed to when we heard about them. A patient
    # who says "I stopped after about a fortnight" has dated an event three
    # weeks before this call, and recording it against the call date would put
    # it in the wrong place in the chronology.
    check_in_date = date_cls.fromisoformat(check_in["date"][:10])
    event_rows = [
        ev.to_row(
            ev.Event(
                kind="check_in",
                label="Check-in call",
                occurred_at=check_in_date,
                precision="day",
                source="derived",
                recorded_at=check_in_date,
            ),
            condition_id=condition["id"],
            check_in_id=check_in["id"],
        )
    ]
    if transcript:
        event_rows += _extract_events(
            transcript,
            on=check_in_date,
            source="patient_reported",
            condition_id=condition["id"],
            check_in_id=check_in["id"],
        )
    created_events = repo.create_events(event_rows) if event_rows else []
    _resolve_scheduled(condition["id"], created_events)

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


@api_view(["GET"])
def events(request):
    """The chronology: what happened when, and what is due.

    The calendar's endpoint. Everything is returned in one call rather than
    paged, because an interval is weeks long and a chronology split across
    requests cannot be read in order.
    """
    condition, error = _condition_or_404(request.query_params.get("condition_id"))
    if error:
        return error

    today = date_cls.today()
    rows = repo.list_events(condition["id"])
    parsed = [ev.from_row(row) for row in rows]

    # Anything already fulfilled is history, not an outstanding due date.
    fulfilled = {r["fulfilled_by"] for r in rows if r.get("fulfilled_by")}
    outstanding = [
        e
        for e, r in zip(parsed, rows)
        if not (r.get("due_at") and not r.get("occurred_at") and r.get("fulfilled_by"))
    ]

    def out(event: ev.Event) -> dict:
        return {
            "id": event.event_id,
            "kind": event.kind,
            "label": event.label,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "due_at": event.due_at.isoformat() if event.due_at else None,
            "precision": event.precision,
            "source": event.source,
            "patient_words": event.patient_words,
            "when": event.when(),
            "reporting_delay_days": event.reporting_delay_days,
            "context_ids": list(event.context_ids),
        }

    return Response(
        {
            "today": today.isoformat(),
            "timeline": [out(e) for e in ev.timeline(outstanding) if e.is_dated],
            "upcoming": [out(e) for e in ev.upcoming(outstanding, today=today)],
            "overdue": [out(e) for e in ev.overdue(outstanding, today=today)],
            "undated": [out(e) for e in outstanding if not e.is_dated and not e.is_scheduled],
            "anchors": {k: v.isoformat() for k, v in ev.anchors(parsed).items()},
            "fulfilled_count": len(fulfilled),
        }
    )


@api_view(["GET", "POST"])
def plan(request):
    """The interval's agenda: what these weeks are meant to establish.

    GET returns the current plan with its coverage — which items the calls
    have reached and which are still outstanding. POST re-plans, for a visit
    recorded before planning existed or one whose planning call failed.
    """
    condition_id = (
        request.query_params.get("condition_id")
        if request.method == "GET"
        else request.data.get("condition_id")
    )
    condition, error = _condition_or_404(condition_id)
    if error:
        return error

    if request.method == "POST":
        visits = repo.list_visits(condition["id"])
        if not visits:
            return Response(
                {"error": "no visits recorded yet"}, status=status.HTTP_400_BAD_REQUEST
            )
        latest = visits[0]
        try:
            context = load_context(CONDITION_CONTEXT)
            built = build_plan(
                summary=latest.get("summary") or {},
                context=context,
                visit_date=latest["date"],
            )
        except IntervalError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except PlanError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        row = repo.create_plan(
            latest["id"], built.data, condition_context=CONDITION_CONTEXT
        )
        return Response(row, status=status.HTTP_201_CREATED)

    current = _load_plan(condition["id"])
    if current is None:
        return Response({"error": "no plan for this interval"}, status=status.HTTP_404_NOT_FOUND)

    try:
        facts, _, _ = _interval_facts(condition["id"])
    except IntervalError:
        facts = None

    week = facts.week if facts else 0
    covered = [
        item_id
        for row in repo.list_check_ins(condition["id"])
        for item_id in (row.get("covered_item_ids") or [])
    ]

    return Response(
        {
            "plan": current.data,
            "week": week,
            "due_now": current.due_items(week),
            "next_call_week": current.next_call_week(week),
            "coverage": plan_coverage(current, covered, week),
        }
    )


@api_view(["POST"])
def brief(request):
    """Generate the next-visit brief from the latest visit + every check-in
    outcome recorded since. The hero screen — see product_doc.md. Requires
    "condition_id" in the body."""
    condition, error = _condition_or_404(request.data.get("condition_id"))
    if error:
        return error

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
    # The chronology, so the brief can say when things happened rather than
    # only that they did. Sequence is often the finding — a symptom that began
    # two weeks before it was reported reads differently from one reported the
    # day it started, and neither is visible from outcomes alone.
    today = date_cls.today()
    event_rows = repo.list_events(condition["id"])
    parsed = [ev.from_row(r) for r in event_rows]
    outstanding = [
        e
        for e, r in zip(parsed, event_rows)
        if not (r.get("due_at") and not r.get("occurred_at") and r.get("fulfilled_by"))
    ]
    if outstanding:
        payload["chronology"] = [
            {"when": e.when(), "what": e.label, "kind": e.kind}
            for e in ev.timeline(outstanding)
            if e.is_dated
        ]

    user_content = json.dumps(payload, indent=2)
    try:
        facts, _, _ = _interval_facts(condition["id"])
        if facts is not None:
            lines = observations(facts) + ev.observations(outstanding, today=today)
            if lines:
                user_content += (
                    # One observation per line, with no bullet character. The
                    # instruction is to reproduce them verbatim, and a model
                    # told that will faithfully reproduce a leading "- " too —
                    # which then shows up as a stray bullet inside a JSON
                    # string. The delimiter must not look like content.
                    "\n\n=== OBSERVATIONS — reproduce each of these verbatim as "
                    "its own entry, do not reword, extend, or prefix them ===\n"
                    + "\n".join(lines)
                )

            # A planned question no call ever reached belongs in the brief's
            # gaps. Without this the brief reads as though the interval covered
            # everything worth covering, which is the one dishonesty that would
            # make it worse than useless to the doctor reading it.
            plan = _load_plan(condition["id"])
            if plan is not None:
                covered = [
                    item_id
                    for row in repo.list_check_ins(condition["id"])
                    for item_id in (row.get("covered_item_ids") or [])
                ]
                missed = plan_coverage(plan, covered, facts.week)["missed"]
                by_id = {item["id"]: item for item in plan.items}
                if missed:
                    user_content += (
                        "\n\n=== PLANNED BUT NEVER ASKED — report each of these "
                        "in `gaps`, as something the record does not cover. Do "
                        "not infer what the answer would have been ===\n"
                        + "\n".join(
                            f"- {by_id[m]['intent']}" for m in missed if m in by_id
                        )
                    )
    except IntervalError:
        pass

    try:
        content = call_llm_json(
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
