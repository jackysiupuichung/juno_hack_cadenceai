"""Persistence for the caretaker context.

Thin by design: the mapping between row and value lives in capture/caretaker.py
next to the type it describes, so this file is the Supabase calls and nothing
else. Same split as the rest of the backend — capture reasons, loop stores.
"""

from __future__ import annotations

from capture.caretaker import CaretakerContext, from_row, to_row

from .supabase_client import get_supabase


def get_caretaker_context(patient_id: str) -> CaretakerContext:
    """The patient's context, or an empty one.

    Never returns None. A patient with no context row and a patient whose
    context is blank are the same thing to every caller — the caretaker knows
    nothing about them — and making callers handle two representations of that
    is how a None reaches a prompt renderer.
    """
    sb = get_supabase()
    rows = (
        sb.table("caretaker_context")
        .select("*")
        .eq("patient_id", patient_id)
        .execute()
        .data
    )
    return from_row(rows[0] if rows else None)


def save_caretaker_context(patient_id: str, context: CaretakerContext) -> dict:
    """Write the context, creating it if this is the first time.

    Upsert on patient_id, which the unique index enforces: this is the standing
    description of one person, and two rows would mean two answers to what to
    call them.
    """
    sb = get_supabase()
    return (
        sb.table("caretaker_context")
        .upsert(to_row(context, patient_id), on_conflict="patient_id")
        .execute()
        .data[0]
    )
