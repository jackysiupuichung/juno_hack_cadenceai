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
import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"

# Which backend answers the summarise call. "anthropic" is the default so an
# unset env behaves exactly as it always has; "codex" routes to an
# OpenAI-compatible endpoint using CODEX_* instead of ANTHROPIC_API_KEY.
PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()

CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-5-codex")
CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://api.openai.com/v1")

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
- The transcript comes from speech recognition and may contain mis-heard
  words. If a word looks garbled and you cannot tell what was meant, do not
  repeat it as though it were a real symptom and do not substitute what you
  think it should have been — that would be guessing at medical content.
  Quote the word as heard and mark it, so the sentence still reads naturally
  — e.g. a symptom the patient described with a word that came through as
  "<word>" (unclear in the recording — please confirm with your doctor).
  Quoting it lets the patient recognise what was mis-heard. Never silently
  correct a garbled word into a different one.
- Capture medication names, dosages, durations, and timings EXACTLY as the
  doctor states them. If a dosage is unclear or inaudible, write
  "unclear — please confirm with your doctor" rather than guessing.
- Extract COMMITMENTS: the concrete things the patient and doctor agreed would
  happen before the next visit. A commitment is trackable — something that can
  later be answered "did this happen?". Examples: starting a medication,
  getting a test, watching for a symptom, booking a follow-up. Prose advice
  with no action is not a commitment.
- source_quote must be one unbroken span copied verbatim from the transcript,
  so it can be checked against the recording word for word. Do not join
  separate remarks with "..." — if no single span covers the whole
  commitment, quote the one that best anchors it.
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


def _codex_client() -> openai.OpenAI:
    if not os.environ.get("CODEX_API_KEY"):
        raise SummariseError(
            "CODEX_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return openai.OpenAI(
        api_key=os.environ["CODEX_API_KEY"],
        base_url=CODEX_BASE_URL,
    )


def _summarise_via_codex(dialogue: str, schema: dict) -> Summary:
    """Summarise through an OpenAI-compatible endpoint.

    Mirrors the Anthropic path's contract — same system prompt, same schema,
    same Summary — but expressed in the Chat Completions shape. The schema is
    sent as a strict json_schema response format, which is that API's
    equivalent of the output_config used on the Anthropic side.
    """
    body = {k: v for k, v in schema.items() if not k.startswith("$")}

    try:
        response = _codex_client().chat.completions.create(
            model=CODEX_MODEL,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "visit_summary",
                    "schema": body,
                    "strict": False,
                },
            },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Here is the consultation transcript:\n\n"
                        f"{dialogue}\n\n"
                        "Organise it into the required JSON structure."
                    ),
                },
            ],
        )
    except openai.APIStatusError as exc:
        raise SummariseError(f"Codex returned {exc.status_code}: {exc.message}") from exc
    except openai.APIConnectionError as exc:
        raise SummariseError(f"Could not reach Codex: {exc}") from exc

    choice = response.choices[0]
    if choice.finish_reason == "content_filter":
        raise SummariseError("Codex declined to summarise this transcript.")

    text = choice.message.content or ""
    if not text.strip():
        if choice.finish_reason == "length":
            raise SummariseError(
                "Codex hit the token limit before returning a summary; "
                "the transcript may be too long."
            )
        raise SummariseError(f"Codex returned no summary (stop: {choice.finish_reason})")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SummariseError(f"Summary was not valid JSON: {exc}. Raw: {text[:500]}") from exc

    usage = response.usage
    return Summary(
        data=_check_shape(data),
        raw=text,
        usage={
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        },
    )


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

    if PROVIDER == "codex":
        return _summarise_via_codex(dialogue, schema)

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
