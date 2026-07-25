"""Persistence for the medication thread.

capture/medication.py models the thread and has no idea a database exists —
correctly, since it is pure logic and heavily tested as such. This module is the
only place that knows how a `Medication` becomes a row and back, so the mapping
lives in one file rather than being re-derived at each call site.

The mapping is mechanical with one decision in it. A `Value` is three columns —
text, source, confirmation — rather than one jsonb field, because "what is still
pending the patient's confirmation" is the query that stops a misread label
reaching a reminder, and it should be an indexed predicate rather than a scan.
The cost is `_FIELDS`, which is the price of that and is paid here only.

What is deliberately not here: any completion of missing values. A row round-
trips to exactly the `Medication` it came from, gaps included. A gap is a
finding, and a persistence layer that helpfully filled one would erase it.
"""

from __future__ import annotations

from capture.medication import (
    Adherence,
    Collection,
    Confirmation,
    Medication,
    Source,
    Value,
)

from .supabase_client import get_supabase

# The five clinical fields, each stored as <field>, <field>_source,
# <field>_confirmation. Ordered as medication.LABEL_FIELDS is, plus the
# instructions that never come off a label.
_FIELDS = ("name", "dosage", "frequency", "duration", "instructions")


def _value_to_columns(field: str, value: Value) -> dict:
    return {
        field: value.text,
        f"{field}_source": value.source.value,
        f"{field}_confirmation": value.confirmation.value,
    }


def _value_from_row(field: str, row: dict) -> Value:
    return Value(
        text=row.get(field) or "",
        source=Source(row.get(f"{field}_source") or Source.CLINICIAN.value),
        confirmation=Confirmation(
            row.get(f"{field}_confirmation") or Confirmation.CONFIRMED.value
        ),
    )


def to_row(medication: Medication, visit_id: str) -> dict:
    """The medication as a database row, minus its id."""
    row = {"visit_id": visit_id}
    for field in _FIELDS:
        row.update(_value_to_columns(field, getattr(medication, field)))
    row.update(
        {
            "collection": medication.collection.value,
            "first_dose_taken": medication.first_dose_taken,
            "reminder_time": medication.reminder_time,
            "adherence": medication.adherence.value,
            "label_seen": medication.label_seen,
            "last_chased_day": medication.last_chased_day,
            "notes": medication.notes,
        }
    )
    return row


def from_row(row: dict) -> Medication:
    """The row as a Medication. The exact inverse of `to_row`."""
    return Medication(
        **{field: _value_from_row(field, row) for field in _FIELDS},
        collection=Collection(row.get("collection") or Collection.UNKNOWN.value),
        first_dose_taken=row.get("first_dose_taken"),
        reminder_time=row.get("reminder_time") or "",
        adherence=Adherence(row.get("adherence") or Adherence.UNKNOWN.value),
        label_seen=bool(row.get("label_seen")),
        last_chased_day=row.get("last_chased_day"),
        notes=list(row.get("notes") or []),
    )


def create_medications(visit_id: str, medications: list[Medication]) -> list[dict]:
    """Seed the thread from what the consultation prescribed.

    Returns [] for a consultation that prescribed nothing — the signal that the
    medication thread is switched off for this interval, not a case to work
    around. Most consultations do not prescribe.
    """
    if not medications:
        return []
    sb = get_supabase()
    rows = [to_row(m, visit_id) for m in medications]
    return sb.table("medications").insert(rows).execute().data


def list_medications_for_visit(visit_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("medications")
        .select("*")
        .eq("visit_id", visit_id)
        .order("created_at")
        .execute()
        .data
    )


def list_medications(condition_id: str) -> list[dict]:
    """Every medication prescribed across this condition's visits.

    Ordered oldest visit first so the thread reads as a history: what was
    started when, and what is still running. A medication from a superseded
    visit is still returned — whether it was stopped is a fact recorded on the
    row, not something to infer from a later prescription existing.
    """
    sb = get_supabase()
    visits = (
        sb.table("visits")
        .select("id")
        .eq("condition_id", condition_id)
        .order("date")
        .execute()
        .data
    )
    visit_ids = [v["id"] for v in visits]
    if not visit_ids:
        return []
    return (
        sb.table("medications")
        .select("*")
        .in_("visit_id", visit_ids)
        .order("created_at")
        .execute()
        .data
    )


def load_medications(condition_id: str) -> list[Medication]:
    """The thread's current state, as capture/medication.py wants it.

    This is the call that fixes the thread resetting every check-in: the state
    comes from what calls have established, not from re-reading the visit
    summary as though no call had happened.
    """
    return [from_row(row) for row in list_medications(condition_id)]


def save_medication(medication_id: str, medication: Medication) -> dict:
    """Write back a medication the call just moved forward.

    The whole row is written rather than a diff. The dataclass is the authority
    on its own consistency — `confirm_label` clearing a rejected value is the
    case that matters — and a field-by-field update lets the row hold a
    combination the dataclass would never produce.

    visit_id is not in the update: a medication does not change which
    consultation prescribed it, and `to_row` needing one is an artefact of it
    also serving inserts.
    """
    sb = get_supabase()
    row = to_row(medication, visit_id="")
    row.pop("visit_id")
    return sb.table("medications").update(row).eq("id", medication_id).execute().data[0]


def sync_from_summary(visit_id: str, medications: list[Medication]) -> list[dict]:
    """Seed a visit's medications once, and never a second time.

    Re-summarising a visit re-runs `from_summary`, which produces medications
    with no thread state at all. Inserting those again would give the patient
    two rows for one tablet, the newer one having forgotten that they collected
    it and take it at 7:30. So a visit that already has medications keeps them:
    what the consultation said has not changed, and what the calls established
    is the part worth protecting.
    """
    existing = list_medications_for_visit(visit_id)
    if existing:
        return existing
    return create_medications(visit_id, medications)
