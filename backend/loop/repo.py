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
    return sb.table("visits").insert(row).execute().data[0]


def get_visit(visit_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("visits").select("*").eq("id", visit_id).execute().data
    return rows[0] if rows else None


def delete_visit(visit_id: str) -> None:
    """Cascades to commitments/outcomes via FK."""
    sb = get_supabase()
    sb.table("visits").delete().eq("id", visit_id).execute()


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
        .eq("status", "pending")
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


def create_check_in(condition_id: str, *, date, transcript, raw) -> dict:
    sb = get_supabase()
    row = {"condition_id": condition_id, "date": date, "transcript": transcript, "raw": raw}
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


def create_brief(condition_id: str, content: dict) -> dict:
    sb = get_supabase()
    return sb.table("briefs").insert({"condition_id": condition_id, "content": content}).execute().data[0]


def delete_patient_cascade(patient_id: str) -> None:
    """The 'Delete everything' consent control. Relies on ON DELETE CASCADE
    foreign keys (see supabase/migrations) to remove every dependent row."""
    sb = get_supabase()
    sb.table("patients").delete().eq("id", patient_id).execute()
