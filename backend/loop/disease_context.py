"""
Loads disease-context reference files (schemas/disease_context.schema.json,
fixtures/*.context.json) — static, hand-authored clinical grounding, not
per-patient data. Kept as versioned files in the repo rather than duplicated
into Supabase, matching the schema's own description of them as a curated
reference a clinician/researcher maintains, not something the app writes.

A condition opts in by setting conditions.disease_context_id to the file's
condition.id slug (e.g. "hypothyroidism").
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


@lru_cache(maxsize=None)
def _load_all() -> dict[str, dict]:
    contexts = {}
    for path in FIXTURES_DIR.glob("*.context.json"):
        data = json.loads(path.read_text())
        slug = data["condition"]["id"]
        contexts[slug] = data
    return contexts


def list_disease_contexts() -> list[dict]:
    """[{id, name, plain_name}, ...] — for a condition-creation picker."""
    return [
        {
            "id": slug,
            "name": ctx["condition"]["name"],
            "plain_name": ctx["condition"]["plain_name"],
        }
        for slug, ctx in _load_all().items()
    ]


def get_disease_context(disease_context_id: str | None) -> dict | None:
    if not disease_context_id:
        return None
    return _load_all().get(disease_context_id)
