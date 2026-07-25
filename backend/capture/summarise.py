"""Turn a consultation transcript into a patient-facing summary and commitments.

This is the stage that makes Cadence not-a-scribe: it reads the transcript and
pulls out the implicit forward-looking plan — the concrete, trackable things
agreed to happen before the next visit. Those commitments are what the interval
is made of, and what the next-visit brief is later built from.

The output is constrained to schemas/visit_summary.schema.json, so a malformed
response is a validation error rather than a silently wrong summary.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"

# Room for the summary plus adaptive thinking on a long consultation.
MAX_TOKENS = 16000

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "visit_summary.schema.json"
)

# Verbatim from product_doc.md. The constraints are the safety boundary: it
# records what was said and never adds clinical judgement of its own.
SYSTEM_PROMPT = """You are a medical scribe assistant working for the PATIENT, not the clinician.
You will receive a transcript, generated from an audio recording, of a
consultation between a patient and a doctor.

Identify who is speaking (DOCTOR or PATIENT), then organise ONLY what was
actually said into the JSON structure below.

Rules:
- Do not add, infer, or invent any medical information.
- Do not give advice of your own. You are recording what was said, nothing more.
- If something was not mentioned in the transcript, return "" or [].
- Capture medication names, dosages, durations, and timings EXACTLY as the
  doctor states them. If a dosage is unclear or inaudible, write
  "unclear — please confirm with your doctor" rather than guessing.
- Extract COMMITMENTS: the concrete things the patient and doctor agreed would
  happen before the next visit. A commitment is trackable — something that can
  later be answered "did this happen?". Examples: starting a medication,
  getting a test, watching for a symptom, booking a follow-up. Prose advice
  with no action is not a commitment.
- Write in plain, patient-friendly language.
- Return valid JSON only, matching the schema. No markdown, no commentary."""


class SummariseError(RuntimeError):
    """The summary could not be produced or did not match the schema."""


@dataclass
class Summary:
    """A visit summary plus the commitments that open the interval."""

    data: dict
    raw: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def commitments(self) -> list[dict]:
        return self.data.get("commitments", [])

    @property
    def medications(self) -> list[dict]:
        return self.data.get("medications", [])

    @property
    def red_flags(self) -> list[str]:
        return self.data.get("red_flags", [])


@lru_cache(maxsize=1)
def load_schema() -> dict:
    """The visit summary JSON schema, which is the contract for this stage."""
    if not SCHEMA_PATH.is_file():
        raise SummariseError(f"Missing schema at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text())


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SummariseError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return anthropic.Anthropic()


def _check_shape(data: object) -> dict:
    """Verify the response has the keys downstream stages read.

    The API enforces the schema, so this guards against a malformed or
    truncated response rather than re-validating field by field.
    """
    if not isinstance(data, dict):
        raise SummariseError(f"Expected a JSON object, got {type(data).__name__}")

    missing = [key for key in load_schema()["required"] if key not in data]
    if missing:
        raise SummariseError(f"Summary is missing required fields: {missing}")

    for i, commitment in enumerate(data["commitments"]):
        absent = [
            key
            for key in ("text", "type", "timeframe", "source_quote")
            if key not in commitment
        ]
        if absent:
            raise SummariseError(f"Commitment {i} is missing fields: {absent}")

    return data


def summarise_transcript(dialogue: str) -> Summary:
    """Summarise a consultation and extract its commitments.

    Args:
        dialogue: The transcript as role-labelled lines, e.g.
            "DOCTOR: ...\\nPATIENT: ...". Role labels matter — the summary
            separates what the doctor said from what the patient reported.

    Returns:
        A Summary whose `data` conforms to the visit summary schema.

    Raises:
        SummariseError: The key is missing, the transcript is empty, or the
            response was unusable.
    """
    if not dialogue or not dialogue.strip():
        raise SummariseError("Cannot summarise an empty transcript.")

    schema = load_schema()

    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {k: v for k, v in schema.items() if not k.startswith("$")},
                }
            },
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Here is the consultation transcript:\n\n"
                        f"{dialogue}\n\n"
                        "Organise it into the required JSON structure."
                    ),
                }
            ],
        )
    except anthropic.APIStatusError as exc:
        raise SummariseError(f"Claude returned {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise SummariseError(f"Could not reach Claude: {exc}") from exc

    if response.stop_reason == "refusal":
        raise SummariseError("Claude declined to summarise this transcript.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text.strip():
        if response.stop_reason == "max_tokens":
            raise SummariseError(
                "Claude hit the token limit before returning a summary; "
                "the transcript may be too long."
            )
        raise SummariseError(f"Claude returned no summary (stop: {response.stop_reason})")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Log the raw response so a schema drift is debuggable.
        raise SummariseError(f"Summary was not valid JSON: {exc}. Raw: {text[:500]}") from exc

    return Summary(
        data=_check_shape(data),
        raw=text,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )
