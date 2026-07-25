"""
LLM calls for the loop app, and the four system prompts (three verbatim from
product_doc.md, plus the chatbot one). Every call returns JSON only; parse
defensively and surface the raw text on failure so a bad response is
debuggable, not silent.

Routes to Anthropic (Claude) by default, or to an OpenAI-compatible endpoint
("Codex") when LLM_PROVIDER=codex — same prompts, same JSON-only contract,
either way.

Where a schema exists in schemas/, it is passed to the API so the provider
enforces the shape rather than the prompt merely asking for it. A summary that
silently loses `commitments` is worse than one that fails loudly: the interval
is built from those commitments, and an empty list looks like a patient who
agreed to nothing rather than like a bug. The chatbot has no schema and passes
none — free-form answers are the point there.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

import anthropic
import openai
from django.conf import settings

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class LLMJSONError(Exception):
    def __init__(self, message, raw_text):
        super().__init__(message)
        self.raw_text = raw_text


@lru_cache(maxsize=8)
def load_schema(name: str) -> dict:
    """A schema from schemas/, stripped of the `$` keys the APIs reject."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.is_file():
        raise LLMJSONError(f"Missing schema at {path}", "")
    body = json.loads(path.read_text())
    return {k: v for k, v in body.items() if not k.startswith("$")}


def _call_anthropic(system_prompt: str, user_content: str, schema: dict | None) -> str:
    kwargs = {}
    if schema is not None:
        kwargs["output_config"] = {
            "format": {"type": "json_schema", "schema": schema}
        }

    response = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY).messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        **kwargs,
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )


def _call_codex(system_prompt: str, user_content: str, schema: dict | None) -> str:
    """Same contract as the Anthropic call, in the Chat Completions shape."""
    if not settings.CODEX_API_KEY:
        raise RuntimeError("CODEX_API_KEY is not set — check your .env")

    if schema is None:
        response_format = {"type": "json_object"}
    else:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": schema, "strict": False},
        }

    client = openai.OpenAI(api_key=settings.CODEX_API_KEY, base_url=settings.CODEX_BASE_URL)
    response = client.chat.completions.create(
        model=settings.CODEX_MODEL,
        response_format=response_format,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content or ""


def call_llm_json(
    system_prompt: str, user_content: str, *, schema_name: str | None = None
) -> dict:
    """Call the configured provider and return parsed JSON.

    Pass `schema_name` (a stem under schemas/, e.g. "visit_summary") to have
    the provider enforce the shape. Without it the model is only asked nicely,
    which is fine for a free-form answer and not fine for anything persisted.
    """
    schema = load_schema(schema_name) if schema_name else None

    raw_text = (
        _call_codex(system_prompt, user_content, schema)
        if settings.LLM_PROVIDER == "codex"
        else _call_anthropic(system_prompt, user_content, schema)
    )
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("LLM did not return valid JSON: %s", raw_text)
        raise LLMJSONError("LLM response was not valid JSON", raw_text) from exc


# --- A. Visit summary + commitment extraction -------------------------------

SUMMARISE_SYSTEM_PROMPT = """\
You are a medical scribe assistant working for the PATIENT, not the clinician.
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
- Return valid JSON only, matching the schema. No markdown, no commentary.

Schema:
{
  "patient_symptoms_summary": "string",
  "doctor_diagnosis": "string",
  "doctor_advice": "string",
  "red_flags": ["string"],
  "medications": [
    { "name": "", "dosage": "", "frequency": "", "duration": "", "instructions": "" }
  ],
  "things_to_avoid": ["string"],
  "lifestyle_advice": ["string"],
  "commitments": [
    {
      "text": "string — what was agreed, in the patient's second person",
      "type": "medication | test | watch_for | followup | lifestyle",
      "timeframe": "string — as stated, e.g. '6 weeks', 'before next visit', ''",
      "source_quote": "string — the line in the transcript this came from"
    }
  ],
  "future_plan": {
    "follow_up_needed": true,
    "date_or_timeframe": "string",
    "purpose": "string"
  }
}
"""


# --- B. Check-in mapping ------------------------------------------------------

CHECKIN_SYSTEM_PROMPT = """\
You are processing a short voice check-in between a patient and a health
companion app. You will receive the check-in transcript and a list of
commitments the patient made at their last consultation.

For each commitment, decide from the transcript alone what happened. Use the
patient's own words wherever possible.

Rules:
- Only report what the patient actually said. If a commitment was not
  discussed, status is "unknown" and the note is "".
- Never judge, advise, or suggest a change. You are recording, not deciding.
- Also capture anything the patient reported that was NOT tied to a
  commitment: new symptoms, side effects, events, or questions they want to
  ask their doctor.
- Return valid JSON only. No markdown, no commentary.

Schema:
{
  "outcomes": [
    {
      "commitment_id": "string",
      "status": "done | not_done | partial | changed | unknown",
      "patient_words": "string — quoted or closely paraphrased",
      "note": "string"
    }
  ],
  "unprompted_reports": ["string"],
  "questions_for_doctor": ["string"]
}
"""


# --- C. Next-visit brief -------------------------------------------------------

BRIEF_SYSTEM_PROMPT = """\
You are preparing a brief that a PATIENT will hand to their DOCTOR at their
next appointment. You will receive: a summary of the last consultation, the
commitments agreed at it, and the outcomes of voice check-ins across the
interval since.

Write four sections: what we agreed, what I did, what happened, what changed.

Rules:
- Every statement must trace to the input. Invent nothing.
- Where a commitment was not kept, say so plainly and without apology or
  euphemism. That is the useful signal for the doctor.
- Where data is missing, say it is missing. Do not pad.
- Do not diagnose, do not suggest treatment, do not recommend a course of
  action. Report the interval; the doctor decides.
- Use rough timing where the check-in dates support it ("around week two").
- Write for a clinician reading in under a minute: dense, specific, no filler.
- Return valid JSON only. No markdown, no commentary.

Schema:
{
  "agreed": [{ "commitment_id": "", "text": "" }],
  "did": [{ "commitment_id": "", "text": "", "status": "done | not_done | partial | changed | unknown" }],
  "happened": [{ "text": "", "approx_timing": "" }],
  "changed": [{ "text": "", "direction": "better | worse | unchanged | unclear" }],
  "open_questions": ["string"],
  "gaps": ["string — what the record does not cover"]
}
"""


# --- D. Ask a question about a visit -----------------------------------------

QA_SYSTEM_PROMPT = """\
You are answering a patient's question about ONE of their recorded
consultations. You will receive the visit's transcript and its structured
summary, then a question.

Rules:
- Answer using ONLY the transcript and summary provided. Do not use outside
  medical knowledge, and do not add advice, dosing guidance, or recommendations
  that are not already in the record.
- Attribute every clinical statement to whoever said it. Write "your doctor
  said your thyroid levels are low", never a bare "your thyroid levels are
  low" — you are reporting an appointment, not making the finding yourself.
  The attribution is what keeps this a record rather than a diagnosis.
- Stop at what was said. Do not explain the mechanism behind a symptom, do not
  say what a result means, and do not extend the doctor's reasoning past where
  they left it, even when the extension seems obvious.
- If the record does not contain the answer, say so plainly rather than
  guessing — set "grounded" to false.
- Quote or closely paraphrase the record where possible.
- Keep the answer conversational and brief (a few sentences).
- Return valid JSON only. No markdown, no commentary.

Schema:
{
  "answer": "string",
  "grounded": true
}
"""
