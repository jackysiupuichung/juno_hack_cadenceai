"""
Supabase data-access helpers for the loop app.

There are no Django ORM models for this data (see models.py) — Supabase
Postgres is the actual store, reached through PostgREST via supabase-py.
Table shapes are defined in supabase/migrations/, matching product_doc.md's
"Data model" section.
"""

from django.conf import settings

from .supabase_client import get_supabase

DEFAULT_PATIENT_NAME = "My Profile"


def get_or_create_patient() -> dict:
    """The single hardcoded patient — there is still no auth/multi-patient."""
    sb = get_supabase()
    patients = sb.table("patients").select("*").eq("id", settings.PATIENT_ID).execute().data
    if not patients:
        patients = (
            sb.table("patients")
            .insert({"id": settings.PATIENT_ID, "name": DEFAULT_PATIENT_NAME})
            .execute()
            .data
        )
    return patients[0]


def update_patient_name(patient_id: str, name: str) -> dict:
    sb = get_supabase()
    return sb.table("patients").update({"name": name}).eq("id", patient_id).execute().data[0]


def list_conditions(patient_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("conditions")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def create_condition(patient_id: str, name: str) -> dict:
    sb = get_supabase()
    return (
        sb.table("conditions")
        .insert({"patient_id": patient_id, "name": name, "status": "active"})
        .execute()
        .data[0]
    )


def get_condition(condition_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("conditions").select("*").eq("id", condition_id).execute().data
    return rows[0] if rows else None


def update_condition_status(condition_id: str, status: str) -> dict:
    sb = get_supabase()
    return sb.table("conditions").update({"status": status}).eq("id", condition_id).execute().data[0]


def delete_condition(condition_id: str) -> None:
    """Cascades to visits/commitments/check_ins/outcomes/briefs via FK."""
    sb = get_supabase()
    sb.table("conditions").delete().eq("id", condition_id).execute()


def list_visits(condition_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("visits")
        .select("*")
        .eq("condition_id", condition_id)
        .order("date", desc=True)
        .execute()
        .data
    )


def create_visit(
    condition_id: str,
    *,
    date,
    care_setting,
    clinician_name,
    organisation,
    organisation_address="",
    transcript,
    summary,
    previous_brief_id=None,
) -> dict:
    sb = get_supabase()
    row = {
        "condition_id": condition_id,
        "date": date,
        "care_setting": care_setting,
        "clinician_name": clinician_name,
        "organisation": organisation,
        "organisation_address": organisation_address,
        "transcript": transcript,
        "summary": summary,
    }
    if previous_brief_id is not None:
        row["previous_brief_id"] = previous_brief_id
    return sb.table("visits").insert(row).execute().data[0]


def get_visit(visit_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("visits").select("*").eq("id", visit_id).execute().data
    return rows[0] if rows else None


def delete_visit(visit_id: str) -> None:
    """Cascades to commitments/outcomes via FK."""
    sb = get_supabase()
    sb.table("visits").delete().eq("id", visit_id).execute()


def create_plan(visit_id: str, content: dict, condition_context: str = "") -> dict:
    """Re-planning an interval replaces its plan — plans.visit_id is unique."""
    sb = get_supabase()
    row = {"visit_id": visit_id, "content": content, "condition_context": condition_context}
    return sb.table("plans").upsert(row, on_conflict="visit_id").execute().data[0]


def get_plan_for_visit(visit_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("plans").select("*").eq("visit_id", visit_id).execute().data
    return rows[0] if rows else None


def get_latest_plan(condition_id: str) -> dict | None:
    """The plan for the condition's most recent visit that has one — earlier
    visits may pre-date planning, so walk back rather than stopping at the first."""
    for visit in list_visits(condition_id):
        plan = get_plan_for_visit(visit["id"])
        if plan:
            return plan
    return None


def create_commitments(visit_id: str, commitments: list[dict]) -> list[dict]:
    if not commitments:
        return []
    sb = get_supabase()
    rows = [
        {
            "visit_id": visit_id,
            "text": c.get("text", ""),
            "type": c.get("type", "lifestyle"),
            "timeframe": c.get("timeframe", ""),
            "source_quote": c.get("source_quote", ""),
            "status": "pending",
        }
        for c in commitments
    ]
    return sb.table("commitments").insert(rows).execute().data


# A commitment is still worth raising on a call while it is in one of these.
# "pending" is the state before anyone has asked; "not_done" and "partial" are
# answers that leave the thing outstanding — a blood test the patient has not
# had yet is exactly what the next call should be chasing. Only "done" and
# "changed" are settled.
#
# This mirrors interval.OPEN_STATUSES, which reasons over check-in JSON rather
# than the database column and so uses "unknown" where the column says
# "pending". Filtering on "pending" alone silently dropped every commitment a
# patient had already said no to, which is precisely the set worth pursuing.
OPEN_COMMITMENT_STATUSES = ("pending", "not_done", "partial")


def get_open_commitments(condition_id: str) -> list[dict]:
    sb = get_supabase()
    visits = sb.table("visits").select("id").eq("condition_id", condition_id).execute().data
    visit_ids = [v["id"] for v in visits]
    if not visit_ids:
        return []
    return (
        sb.table("commitments")
        .select("*")
        .in_("visit_id", visit_ids)
        .in_("status", list(OPEN_COMMITMENT_STATUSES))
        .execute()
        .data
    )


def get_commitments_for_visit(visit_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("commitments").select("*").eq("visit_id", visit_id).execute().data


def update_commitment_status(commitment_id: str, status: str) -> None:
    sb = get_supabase()
    sb.table("commitments").update({"status": status}).eq("id", commitment_id).execute()


def list_check_ins(condition_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("check_ins")
        .select("*, outcomes(*)")
        .eq("condition_id", condition_id)
        .order("date", desc=True)
        .execute()
        .data
    )


def create_check_in(
    condition_id: str, *, date, transcript, raw, covered_item_ids: list[str] | None = None
) -> dict:
    sb = get_supabase()
    row = {
        "condition_id": condition_id,
        "date": date,
        "transcript": transcript,
        "raw": raw,
        "covered_item_ids": covered_item_ids or [],
    }
    return sb.table("check_ins").insert(row).execute().data[0]


def create_outcomes(check_in_id: str, outcomes: list[dict]) -> list[dict]:
    if not outcomes:
        return []
    sb = get_supabase()
    rows = [
        {
            "check_in_id": check_in_id,
            "commitment_id": o["commitment_id"],
            "status": o.get("status", "unknown"),
            "patient_words": o.get("patient_words", ""),
            "note": o.get("note", ""),
        }
        for o in outcomes
    ]
    return sb.table("outcomes").insert(rows).execute().data


def get_outcomes_for_commitments(commitment_ids: list[str]) -> list[dict]:
    if not commitment_ids:
        return []
    sb = get_supabase()
    return (
        sb.table("outcomes")
        .select("*, check_ins(date)")
        .in_("commitment_id", commitment_ids)
        .execute()
        .data
    )


def create_events(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    sb = get_supabase()
    return sb.table("events").insert(rows).execute().data


def list_events(condition_id: str) -> list[dict]:
    """Chronological order, undated events last — an event with no occurred_at
    is either scheduled or something the patient never dated, and neither
    belongs at the head of the timeline."""
    sb = get_supabase()
    return (
        sb.table("events")
        .select("*")
        .eq("condition_id", condition_id)
        .order("occurred_at", desc=False, nullsfirst=False)
        .execute()
        .data
    )


def list_upcoming_events(condition_id: str, *, before) -> list[dict]:
    """Scheduled events still outstanding — due, and not yet happened."""
    sb = get_supabase()
    return (
        sb.table("events")
        .select("*")
        .eq("condition_id", condition_id)
        .not_.is_("due_at", "null")
        .is_("occurred_at", "null")
        .lte("due_at", before)
        .order("due_at", desc=False)
        .execute()
        .data
    )


def get_events_for_visit(visit_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("events").select("*").eq("visit_id", visit_id).execute().data


def get_events_for_check_in(check_in_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("events").select("*").eq("check_in_id", check_in_id).execute().data


def mark_event_fulfilled(event_id: str, fulfilled_by_event_id: str) -> dict:
    sb = get_supabase()
    return (
        sb.table("events")
        .update({"fulfilled_by": fulfilled_by_event_id})
        .eq("id", event_id)
        .execute()
        .data[0]
    )


def delete_events_for_check_in(check_in_id: str) -> None:
    """Re-processing a check-in re-extracts its events, so clear the old ones
    first rather than accumulating a duplicate of every dated thing said."""
    sb = get_supabase()
    sb.table("events").delete().eq("check_in_id", check_in_id).execute()


def list_briefs(condition_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("briefs")
        .select("*")
        .eq("condition_id", condition_id)
        .order("generated_at", desc=True)
        .execute()
        .data
    )


def get_latest_brief(condition_id: str) -> dict | None:
    briefs = list_briefs(condition_id)
    return briefs[0] if briefs else None


def get_brief(brief_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("briefs").select("*").eq("id", brief_id).execute().data
    return rows[0] if rows else None


def create_brief(condition_id: str, content: dict) -> dict:
    sb = get_supabase()
    return sb.table("briefs").insert({"condition_id": condition_id, "content": content}).execute().data[0]


def delete_patient_cascade(patient_id: str) -> None:
    """The 'Delete everything' consent control. Relies on ON DELETE CASCADE
    foreign keys (see supabase/migrations) to remove every dependent row."""
    sb = get_supabase()
    sb.table("patients").delete().eq("id", patient_id).execute()
