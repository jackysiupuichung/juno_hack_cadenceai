"""The next-visit brief: an account of the interval a visit opened.

This is the artifact the patient hands their doctor. It is only impressive
because of what it is made of — not a summary of the last consultation, which
is a memory aid anyone can build, but a record of the weeks after it: what was
agreed, what actually happened, and what the record does not cover.

The model composes the narrative. It does not compose the clinical statements.
Anything that measures this interval against the guideline — a test due around
week seven that has not happened, a marker not met by the week it usually is —
is written by interval.observations() in Python and handed over as a line to
reproduce verbatim. That split is deliberate and it is the same one the
check-in uses: "your doctor asked for repeat bloods around week seven; that was
three weeks ago" is a fact about the record, while "your dose may be too high"
is a diagnosis. Giving the model the facts pre-written means it never has the
opportunity to produce the second kind.

The other rule that matters here is that a thin interval must produce a thin
brief. If nobody checked in, the brief says so in gaps[] rather than padding
the sections out — a doctor who cannot tell a quiet interval from an unrecorded
one is worse off than one holding nothing at all.
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

from .interval import IntervalFacts, observations
from .trackers import Series
from .trackers import observations as tracker_observations

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-5")
CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://api.openai.com/v1")

MAX_TOKENS = 8000

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "brief.schema.json"

SYSTEM_PROMPT = """You are preparing a one-page brief that a patient will hand to their doctor \
at their next appointment. The doctor has about two minutes and has not seen \
this patient in months. Your reader is the doctor; your author is the patient.

You will be given: the commitments made at the last visit, the record of every \
check-in call across the interval with the week each happened, and a list of \
factual observations about the interval that have already been written for you.

Write four sections: what we agreed, what I did, what happened, what changed.

Rules:
- Every line must trace to something in the record. If the record does not \
contain it, it does not go in the brief.
- Reproduce the supplied observations verbatim into the appropriate section. \
Do not extend them, soften them, or draw a conclusion from them.
- State not-done plainly. "Did not have the blood test" — not "has not yet had \
the opportunity to". The gap is the signal the doctor needs, and softening it \
destroys the only useful thing about it.
- Use approx_timing only where a check-in's week supports it: "around week \
four". Otherwise leave it empty.
- Self-rated scores belong in "what changed", reproduced with their numbers and \
weeks exactly as supplied. Keep the series — "6 at week 1, 3 at week 7" is the \
useful form; "improved" is not, and deciding a rating is an improvement is not \
yours to do. A rating is what the patient reported feeling, never a measurement \
of the condition and never evidence about the treatment.
- Never diagnose, never attribute a cause to a symptom, never comment on a \
dose or on whether treatment is working, never interpret a result, never \
recommend a test or a referral. You report the interval; the doctor decides.
- Put in gaps[] what the record does not cover: weeks with no check-in, \
commitments never discussed, questions never asked. An empty interval is \
honest output. Do not pad the other sections to disguise a thin record.
- Write for a clinician: dense, factual, no reassurance, no filler.
- Return valid JSON only, matching the schema. No markdown, no commentary."""


class BriefError(RuntimeError):
    """The brief could not be produced or did not match the schema."""


@dataclass
class Brief:
    """The next-visit brief, conforming to brief.schema.json."""

    data: dict
    raw: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def agreed(self) -> list[dict]:
        return self.data.get("agreed", [])

    @property
    def did(self) -> list[dict]:
        return self.data.get("did", [])

    @property
    def happened(self) -> list[dict]:
        return self.data.get("happened", [])

    @property
    def changed(self) -> list[dict]:
        return self.data.get("changed", [])

    @property
    def gaps(self) -> list[str]:
        return self.data.get("gaps", [])

    @property
    def open_questions(self) -> list[str]:
        return self.data.get("open_questions", [])


@lru_cache(maxsize=1)
def load_schema() -> dict:
    if not SCHEMA_PATH.is_file():
        raise BriefError(f"Missing schema at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text())


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise BriefError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic()


def _codex_client() -> openai.OpenAI:
    if not os.environ.get("CODEX_API_KEY"):
        raise BriefError("CODEX_API_KEY is not set.")
    return openai.OpenAI(api_key=os.environ["CODEX_API_KEY"], base_url=CODEX_BASE_URL)


def _payload(
    facts: IntervalFacts,
    check_ins: list[dict],
    series: list[Series] | None = None,
) -> str:
    """Everything the brief is made of, as one document.

    The observations go in as a distinct block labelled "reproduce verbatim",
    rather than mixed into the data, so the model reads them as text to carry
    across rather than as findings to reason about.
    """
    body = {
        "interval": {
            "condition": facts.condition_name,
            "visit_date": facts.visit_date.isoformat(),
            "today": facts.today.isoformat(),
            "weeks_elapsed": facts.week,
            "check_ins_held": facts.previous_check_in_weeks,
        },
        "agreed_at_the_visit": [
            {
                "commitment_id": c.commitment_id,
                "text": c.text,
                "type": c.type,
                "timeframe": c.timeframe,
                "current_status": c.status,
            }
            for c in facts.commitments
        ],
        "check_ins": [
            {
                "week": c.get("week") or (c.get("_meta") or {}).get("week"),
                "outcomes": c.get("outcomes", []),
                "symptoms_reported": c.get("symptom_mentions", []),
                "unprompted_reports": c.get("unprompted_reports", []),
                "questions_for_doctor": c.get("questions_for_doctor", []),
            }
            for c in check_ins
        ],
    }

    lines = [json.dumps(body, indent=2)]

    # A rated series is exactly the material a model will editorialise if it is
    # handed the numbers and left to describe them, so it arrives already
    # written as sentences, in the same verbatim block as everything else that
    # measures this interval. The model carries the line across; it does not
    # decide what four points of movement mean.
    facts_to_reproduce = observations(facts) + tracker_observations(series or [])
    if facts_to_reproduce:
        lines.append(
            "\n=== OBSERVATIONS — reproduce these verbatim, do not reword or "
            "extend them ===\n" + "\n".join(f"- {line}" for line in facts_to_reproduce)
        )

    if not check_ins:
        lines.append(
            "\n=== NOTE ===\nNo check-ins were recorded in this interval. Say so "
            "in gaps[] and leave the other sections thin. Do not pad."
        )

    return "\n".join(lines)


def _check_shape(data: object) -> dict:
    if not isinstance(data, dict):
        raise BriefError(f"Expected a JSON object, got {type(data).__name__}")
    missing = [key for key in load_schema()["required"] if key not in data]
    if missing:
        raise BriefError(f"Brief is missing required fields: {missing}")
    return data


def build_brief(
    *,
    facts: IntervalFacts,
    check_ins: list[dict],
    series: list[Series] | None = None,
) -> Brief:
    """Compose the next-visit brief from the interval's record.

    Args:
        facts: The interval, from compute_interval_facts.
        check_ins: Every check-in record of the interval, oldest first.
        series: The scored symptoms and their points, from trackers.collect.
            Their movement is the one part of the interval that carries a
            direction, so it arrives pre-written rather than as numbers.

    Returns:
        A Brief whose `data` conforms to brief.schema.json.

    Raises:
        BriefError: The key is missing, or the response was unusable.
    """
    schema = {k: v for k, v in load_schema().items() if not k.startswith("$")}
    user_content = _payload(facts, list(check_ins), series)

    if PROVIDER == "codex":
        try:
            response = _codex_client().chat.completions.create(
                model=CODEX_MODEL,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "brief", "schema": schema, "strict": False},
                },
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
        except openai.APIStatusError as exc:
            raise BriefError(f"Codex returned {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise BriefError(f"Could not reach Codex: {exc}") from exc

        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise BriefError("Codex declined to produce this brief.")
        text = choice.message.content or ""
        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        }
    else:
        try:
            response = _client().messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIStatusError as exc:
            raise BriefError(f"Claude returned {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise BriefError(f"Could not reach Claude: {exc}") from exc

        if response.stop_reason == "refusal":
            raise BriefError("Claude declined to produce this brief.")
        text = next((b.text for b in response.content if b.type == "text"), "")
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

    if not text.strip():
        raise BriefError("The model returned an empty brief.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BriefError(f"Brief was not valid JSON: {exc}. Raw: {text[:500]}") from exc

    return Brief(data=_check_shape(data), raw=text, usage=usage)


def render(brief: Brief) -> str:
    """The brief as plain text, for a terminal or a print view."""
    out = ["WHAT WE AGREED"]
    out += [f"  · {row['text']}" for row in brief.agreed] or ["  (nothing recorded)"]

    out += ["", "WHAT I DID"]
    out += [
        f"  · [{row['status']}] {row['text']}" for row in brief.did
    ] or ["  (nothing recorded)"]

    out += ["", "WHAT HAPPENED"]
    out += [
        f"  · {row['text']}" + (f" ({row['approx_timing']})" if row.get("approx_timing") else "")
        for row in brief.happened
    ] or ["  (nothing recorded)"]

    out += ["", "WHAT CHANGED"]
    out += [
        f"  · [{row['direction']}] {row['text']}" for row in brief.changed
    ] or ["  (nothing recorded)"]

    if brief.open_questions:
        out += ["", "QUESTIONS FOR THE DOCTOR"]
        out += [f"  ? {q}" for q in brief.open_questions]

    if brief.gaps:
        out += ["", "WHAT THIS RECORD DOES NOT COVER"]
        out += [f"  · {g}" for g in brief.gaps]

    out += [
        "",
        "Prepared by the patient from recorded consultations and self-reported "
        "check-ins.",
    ]
    return "\n".join(out)
