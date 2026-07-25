"""The caretaker: decides what this interval has to establish, before any call.

A consultation ends and an interval opens. Someone has to work out what the
weeks ahead need to find out — which of the things agreed actually matter to
chase, which clinical patterns are worth asking about even though the patient
would never raise them, and roughly when each becomes worth a phone call. In a
well-resourced service a person does that. Here it is one Claude call made once,
at the moment the visit is summarised, and the result is persisted.

Why a plan at all, when checkin.py already reasons its way through a call:

  - It is decided in the calm. The planner sees the whole visit and the whole
    disease context with no turn budget and no patient waiting. The agent on the
    call has ten turns and someone tiring on the other end.
  - It makes the interval auditable in advance. "This is what we intend to find
    out over the next seven weeks" is inspectable before anything happens; the
    agent's per-turn reasoning is only inspectable afterwards.
  - It makes not-asking visible. A plan item that no call ever covered is a
    finding — it is how the brief can say a question went unasked rather than
    silently omitting it.

What the plan is not: a script. It fixes the agenda, not the wording. Items are
intents ("establish whether the repeat blood test has happened"), never
sentences to read aloud, and the agent remains free to depart from them when the
conversation calls for it. The division of labour from checkin.py holds — the
planner decides what is worth knowing, Python decides when an item is eligible,
and neither of them says anything clinical to the patient.
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

from .interval import IntervalFacts, commitment_id

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-5")
CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://api.openai.com/v1")

MAX_TOKENS = 4000

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "check_in_plan.schema.json"
)

SYSTEM_PROMPT = """You are the caretaker behind Cadence. A patient has just had an \
appointment, and you are deciding what the interval before their next one needs \
to establish.

You are not writing a script and you are not phoning anyone. You are setting an \
agenda that an agent will use to run short voice check-ins over the coming \
weeks. It will read your plan, then decide its own wording, ordering and \
follow-ups on the call. Give it aims, not sentences.

You will be given the summary of the appointment that just happened — what was \
said, what was agreed — and the full clinical context for this condition: what \
the guidance says to watch for, the expected trajectory, the monitoring \
intervals, and suggested probes, all with their ids.

How to build the agenda:
- Start from what was actually agreed at this appointment. Every commitment \
that could plausibly not happen, or could happen and go badly, deserves an item.
- Then add what the clinical context says matters that the appointment did not \
cover. The check_in_probes are a well-designed starting point; treat their \
ask_from_week and priority as informed judgement you may depart from.
- Weight heavily toward patterns the patient would never volunteer. Some \
symptoms matter precisely because they look unrelated to the original \
complaint, so the patient does not connect them and an open question will never \
surface them. Mark those ask_directly and give them priority 1.
- Set from_week honestly. An item asked before it could possibly have happened \
wastes a question on someone whose scarcest resource is attention.
- Cite your grounding in context_ids and commitment_ids. An item that cites \
nothing had better come from something explicit in the appointment.

The call schedule:
- Few calls, well placed. This person tires easily. Three or four across a \
seven-week interval is generous; more is a burden, not diligence.
- Place calls where something will have changed — after a test was due, after \
the point where a side effect would show, before the next appointment.

What you must not do:
- Never plan to give advice. No item may aim to tell the patient what to do \
about a symptom, a dose, or a result. Items establish what happened; they do \
not intervene.
- Never plan to diagnose, interpret a result, or judge whether treatment is \
working. If the interval needs that question answered, the item is to gather \
what the doctor will need in order to answer it.
- Do not plan to alarm. A red flag in the context is something to ask about, \
not something to warn about pre-emptively.

Return valid JSON only, matching the schema. No markdown, no commentary."""


class PlanError(RuntimeError):
    """The plan could not be produced or did not match the schema."""


@dataclass
class CheckInPlan:
    """A persisted agenda for one interval, plus provenance."""

    data: dict
    raw: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def interval_goal(self) -> str:
        return self.data.get("interval_goal", "")

    @property
    def items(self) -> list[dict]:
        return self.data.get("items", [])

    @property
    def call_schedule(self) -> list[dict]:
        return self.data.get("call_schedule", [])

    @property
    def reasoning(self) -> str:
        return self.data.get("reasoning", "")

    def due_items(self, week: int) -> list[dict]:
        """Agenda items eligible this week, most important first.

        Eligibility is arithmetic over from_week/until_week, so it is decided
        here rather than by the agent — the same division as everywhere else in
        this codebase. The agent still chooses which of the eligible items to
        actually spend its turns on.
        """
        eligible = [
            item
            for item in self.items
            if week >= item.get("from_week", 0)
            and (item.get("until_week") is None or week <= item["until_week"])
        ]
        return sorted(eligible, key=lambda i: i.get("priority", 3))

    def next_call_week(self, after_week: int) -> int | None:
        """The next scheduled call strictly after `after_week`, if any."""
        weeks = sorted(
            c["week"] for c in self.call_schedule if c.get("week", 0) > after_week
        )
        return weeks[0] if weeks else None


@lru_cache(maxsize=1)
def load_schema() -> dict:
    if not SCHEMA_PATH.is_file():
        raise PlanError(f"Missing schema at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text())


def response_schema() -> dict:
    """The plan schema, stripped of the keys the APIs reject."""
    schema = json.loads(json.dumps(load_schema()))
    schema.pop("$schema", None)
    schema.pop("$id", None)
    return schema


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise PlanError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return anthropic.Anthropic()


def _codex_client() -> openai.OpenAI:
    if not os.environ.get("CODEX_API_KEY"):
        raise PlanError(
            "CODEX_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return openai.OpenAI(api_key=os.environ["CODEX_API_KEY"], base_url=CODEX_BASE_URL)


def _commitment_lines(summary: dict) -> str:
    """The visit's commitments with the ids the plan must cite.

    Ids are derived the same way interval.py derives them, so an item's
    commitment_ids line up with the facts the agent is handed on the call.
    """
    lines = []
    for i, c in enumerate(summary.get("commitments", [])):
        timeframe = f" [{c['timeframe']}]" if c.get("timeframe") else ""
        lines.append(
            f"  [{commitment_id(i)}] ({c.get('type', '')}) {c.get('text', '')}{timeframe}"
        )
    return "\n".join(lines) or "  (none recorded at this visit)"


def _drug_lines(summary: dict, context: dict) -> str:
    """What the patient is actually taking, as stated at the visit.

    Kept separate from the commitments because a medication the patient was
    already on is not something they agreed to at this appointment, but it is
    exactly what the over-treatment patterns in the context hang off — the plan
    needs to see it to know those patterns are live at all.
    """
    lines = []
    for med in summary.get("medications") or []:
        if isinstance(med, dict):
            # Keys per visit_summary.schema.json. Dosage and duration are the
            # fields the over-treatment patterns hang off, so they are shown
            # even when the doctor stated them vaguely ("a very low dose") —
            # the vagueness is itself something the interval may need to
            # resolve, and hiding it would make the plan look better informed
            # than it is.
            detail = ", ".join(
                str(med[k])
                for k in ("dosage", "frequency", "duration", "instructions")
                if med.get(k)
            )
            name = med.get("name", "")
            lines.append(f"  - {name}{(' — ' + detail) if detail else ''}")
        elif med:
            lines.append(f"  - {med}")

    typical = context.get("condition", {}).get("typical_treatment", "")
    if typical:
        lines.append(f"  (usual treatment for this condition: {typical})")
    return "\n".join(lines) or "  (none recorded)"


def _build_user_content(summary: dict, context: dict, visit_date: str) -> str:
    return (
        f"=== THE APPOINTMENT ({visit_date}) ===\n"
        f"{json.dumps(summary, indent=2)}\n\n"
        f"=== WHAT WAS AGREED — cite these ids in commitment_ids ===\n"
        f"{_commitment_lines(summary)}\n\n"
        f"=== WHAT THEY ARE TAKING ===\n"
        f"{_drug_lines(summary, context)}\n\n"
        f"=== CLINICAL CONTEXT FOR "
        f"{context.get('condition', {}).get('name', '').upper()} — "
        f"cite these ids in context_ids ===\n"
        f"{json.dumps(context, indent=2)}\n\n"
        "Produce the plan for this interval."
    )


def _system_prompt(context: dict) -> str:
    prohibited = "\n".join(
        f"- {line}" for line in context.get("safety", {}).get("prohibited_outputs", [])
    )
    framing = context.get("safety", {}).get("framing_rule", "")
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"=== THE BOUNDARY ===\n{framing}\n\n"
        f"No item in your plan may aim to produce any of the following:\n{prohibited}"
    )


def _check_plan(data: object) -> dict:
    if not isinstance(data, dict):
        raise PlanError(f"Expected a JSON object, got {type(data).__name__}")
    missing = [key for key in load_schema()["required"] if key not in data]
    if missing:
        raise PlanError(f"Plan is missing required fields: {missing}")
    return data


def build_plan(*, summary: dict, context: dict, visit_date: str) -> CheckInPlan:
    """Produce the interval's agenda from the visit and the disease context.

    Args:
        summary: A visit summary conforming to visit_summary.schema.json.
        context: A disease context, from interval.load_context.
        visit_date: ISO date of the consultation — the clock's origin, so the
            planner can reason about what will have happened by which week.

    Returns:
        A CheckInPlan whose `data` conforms to check_in_plan.schema.json.
    """
    system = _system_prompt(context)
    user_content = _build_user_content(summary, context, visit_date)
    schema = response_schema()

    if PROVIDER == "codex":
        try:
            response = _codex_client().chat.completions.create(
                model=CODEX_MODEL,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "check_in_plan",
                        "schema": schema,
                        "strict": False,
                    },
                },
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
        except openai.APIStatusError as exc:
            raise PlanError(f"Codex returned {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise PlanError(f"Could not reach Codex: {exc}") from exc

        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise PlanError("Codex declined to plan this interval.")
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
                system=system,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIStatusError as exc:
            raise PlanError(f"Claude returned {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise PlanError(f"Could not reach Claude: {exc}") from exc

        if response.stop_reason == "refusal":
            raise PlanError("Claude declined to plan this interval.")
        text = next((b.text for b in response.content if b.type == "text"), "")
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

    if not text.strip():
        raise PlanError(f"{PROVIDER} returned an empty plan")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"Plan was not valid JSON: {exc}. Raw: {text[:500]}") from exc

    return CheckInPlan(data=_check_plan(data), raw=text, usage=usage)


def as_agent_brief(plan: CheckInPlan, week: int) -> str:
    """The plan rendered for the check-in agent's system prompt.

    Only the items eligible this week are shown, and they are shown as aims
    rather than questions, because an agent handed a list of sentences reads
    them out. Items not yet due are summarised as a count so the agent knows the
    interval continues past this call and need not force everything into it.
    """
    if not plan.items:
        return ""

    due = plan.due_items(week)
    lines = [f"Goal for this interval: {plan.interval_goal}"]

    focus = next(
        (c["focus"] for c in plan.call_schedule if c.get("week") == week), ""
    )
    if focus:
        lines.append(f"This call was planned for: {focus}")

    if due:
        lines.append(
            "\nOn the agenda for this call (aims, not questions — phrase them "
            "yourself, in your own words, and follow what they say):"
        )
        for item in due:
            direct = " — ask about this directly, they will not raise it" if item.get("ask_directly") else ""
            lines.append(f"  [{item['id']}] p{item.get('priority', 3)} {item['intent']}{direct}")
            if item.get("why"):
                lines.append(f"      why: {item['why']}")
    else:
        lines.append("\nNothing on the agenda is due yet this week.")

    later = len(plan.items) - len(due)
    if later > 0:
        lines.append(
            f"\n{later} further item(s) become due later in the interval — "
            "they do not need forcing into this call."
        )

    upcoming = plan.next_call_week(week)
    if upcoming is not None:
        lines.append(f"The next call is planned for week {upcoming}.")

    return "\n".join(lines)


def coverage(plan: CheckInPlan, covered: list[str], week: int) -> dict:
    """Which planned items the calls actually reached, and which they missed.

    A planned item that no call ever covered is a finding in its own right — it
    is the difference between "the patient said the test was fine" and "nobody
    ever asked about the test". The brief reports the second honestly rather
    than leaving a silent gap, which is the whole point of writing the agenda
    down in advance.
    """
    seen = set(covered)
    due = plan.due_items(week)
    return {
        "covered": [item["id"] for item in due if item["id"] in seen],
        "missed": [item["id"] for item in due if item["id"] not in seen],
        "not_yet_due": [
            item["id"] for item in plan.items if item not in due
        ],
    }
