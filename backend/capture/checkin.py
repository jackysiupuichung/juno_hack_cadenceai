"""The check-in agent: reasons over the disease context, decides what to ask.

This is the part of Cadence that spans the interval. The agent is given the
whole curated disease context — every probe, red flag, expected trajectory and
monitoring interval, with its citations — plus the facts of this particular
interval, and it works out its own line of questioning. It is not walking a
fixed script: it decides what matters at week 7 for this patient, follows what
the patient actually says, and stops when it has what it needs.

That autonomy is the point. The highest-value catch in hypothyroidism is the
over-replacement cluster — palpitations, tremor, heat intolerance, insomnia,
weight loss — symptoms that look nothing like the original complaint, so a
patient never volunteers them and a fixed script only finds them if someone
thought to write the question. An agent reading the context can see why those
symptoms matter and pursue them when something in the conversation suggests it.

Two things are deliberately kept out of the agent's hands, because more
autonomy makes both more important rather than less:

  - Counting. Whether a cluster has fired is arithmetic over mentions
    accumulated across calls weeks apart (see redflags.py). A model asked to
    count across its own prior turns will sometimes be wrong, and this is the
    catch the whole product rests on.
  - Saying anything clinical. The agent has more rope here than a scripted one
    — it can see typical_treatment, dose language, guideline rationale — so
    everything it says passes through safety.py, and any patient-facing warning
    is copied verbatim from the context rather than composed.

The agent reasons and plans. Python counts and constrains.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import anthropic
import openai
from dotenv import load_dotenv

from . import safety
from .caretaker import CaretakerContext
from .caretaker import as_agent_brief as caretaker_as_agent_brief
from .interval import IntervalFacts, as_agent_brief, watch_for_vocabulary
from .medication import Medication
from .medication import as_agent_brief as medication_as_agent_brief
from .trackers import Series
from .trackers import as_agent_brief as trackers_as_agent_brief
from .plan import CheckInPlan
from .plan import as_agent_brief as plan_as_agent_brief
from .redflags import FiredFlag, evaluate_flags

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-5")
CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://api.openai.com/v1")

MAX_TOKENS = 4000

# A hard stop on the conversation regardless of what the agent decides. Fatigue
# is the core symptom of the population this serves, so the turn budget is a
# guarantee to the patient, not a hint to the model.
MAX_TURNS = 10

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "check_in_turn.schema.json"
)

INTERVAL_FRAMING = """You are Cadence, phoning a patient between appointments. You work for the \
patient, not for their clinic. You are not their doctor, and you are not a \
triage service.

Your job is to find out how the interval since their appointment has actually \
gone, and to record it accurately enough that their next appointment can start \
from what happened rather than from nothing.

You will be given two things: the facts of this interval — what was agreed, \
how many weeks have passed, what has already been reported — and the full \
clinical context for this condition, including what the guidance says to watch \
for and why. Read both and decide for yourself what is worth asking on this \
call. You are not working from a script.

How to decide what to ask:
- The context's check_in_probes are a well-designed starting point, not an \
obligation. Their ask_from_week and priority tell you what the authors thought \
mattered when. Use that judgement; you may depart from it when this \
particular interval calls for something else.
- Pay attention to what the patient would never think to mention. Some \
symptoms matter precisely because they look unrelated to the original \
complaint, so the patient does not connect them and will not volunteer them. \
An open question rarely surfaces those. If the context flags such a pattern, \
ask about it directly.
- Follow what the patient actually says. If they open a thread worth pulling, \
pull it, even if nothing in the context anticipated it.
- Do not re-ask what is already settled. Commitments marked done, and symptoms \
already recorded this interval, do not need revisiting unless something has \
changed."""

# Everything below applies to every call regardless of when in the interval it
# falls: how to speak, where the line is, and how to write the record down. Kept
# apart from the framing above so the day-after call can replace what the call
# is for without restating any of it — a second copy of the boundary rules is a
# second copy to drift.
SHARED_RULES = """How to talk:
- One question per turn. Short, warm, answerable in one breath.
- This person tires easily. Aim to be done in six or seven exchanges. Brevity \
is care, not curtness.
- Acknowledge what they just said before moving on. Do not stack questions.

What you must not do:
- Never diagnose. Never explain why a symptom might be happening. Never \
comment on a medication, a dose, or whether treatment is working. Never \
interpret a test result. Never recommend a test, a referral, or a change.
- If asked a clinical question, say plainly that it is one for their doctor, \
record it in questions_for_doctor, and move on. Do not hedge into an answer.
- If the patient describes something the context lists as needing urgent \
attention, you may tell them so — but only in the context's own words, which \
will be supplied to you. Do not compose your own warning and do not explain \
what you think it means.

Medication, when something was prescribed:
- Never state or infer a name, dose, frequency or instruction the clinician did \
not give or the pharmacy label did not print. If a value is marked as not \
established, it is not established — ask the patient, or ask them to photograph \
the label. Do not complete it from the drug name or from what is usual.
- When you read a value back for confirmation, say where it came from, and get \
a yes or no before treating it as settled. A value the patient has not agreed \
to is not yet a value.
- You may repeat the clinician's own timing instruction. You may not add a \
timing rule they did not give.

The scored questions, when the plan has any:
- Ask each one exactly as written, once per call. This is the only thing you \
do not phrase yourself, and rewording it is not a small liberty: the number is \
compared with the ones from earlier calls, and a different question produces a \
number that means something different. Ask it verbatim even where you would \
have said it better.
- Do not tell them what they said last time. Someone reminded of their previous \
score gives it again.
- If they will not give a number, take what they say and move on. Record the \
tracker with a null value and their words. Never estimate the number yourself, \
and never ask twice.

Recording what you hear:
- Map symptoms onto the context's own vocabulary where they plainly match. \
Where they do not plainly match, put them in unprompted_reports in the \
patient's own words. A wrong match is worse than no match.
- Record an outcome for a commitment only when the patient actually addressed \
it. Silence is not "not_done"; leave it out.
- patient_words must be their words, quoted or closely paraphrased — never \
your summary of them.
- reasoning is one sentence on why you asked what you asked. Because you are \
choosing your own questions, this is the only record of why the call went the \
way it did. Write it so someone reviewing the call can follow your thinking.

Return valid JSON only, matching the schema. No markdown, no commentary."""

SYSTEM_PROMPT = f"{INTERVAL_FRAMING}\n\n{SHARED_RULES}"

# The day-after call is a different conversation from the ones that follow, and
# giving it the interval persona produces the wrong call entirely: an agent told
# to find out "how the interval has gone" on day one asks a patient who has had
# no interval yet how their symptoms are, and never gets to whether the
# prescription was collected. What is replaced is only the framing — everything
# after "How to talk" in SYSTEM_PROMPT applies unchanged, and is appended.
FIRST_CONTACT_FRAMING = """You are Cadence, phoning a patient the day after their \
appointment. You work for the patient, not for their clinic. You are not their \
doctor, and you are not a triage service.

This is the first contact of the interval, and it is a short one. Nothing has \
happened yet — do not ask how they have been getting on, or whether anything has \
changed, because there has been no time for either.

Your job on this call is to confirm the plan is real and workable. Not whether \
it is the right plan — that is not yours to judge — but whether it is actually \
going to happen:
- If something was prescribed: have they collected it, have they taken the \
first dose, what does the label actually say, and what time each day will they \
take it. That last one seeds their daily reminders, so do not end the call \
without it.
- Whatever was agreed: is anything about the instructions unclear.
- Is there anything from the appointment they did not understand.

If they did not understand something the clinician said, you may explain it in \
plainer terms — but only what the clinician actually said, attributed to them, \
and never with anything added. If their question goes beyond what the \
appointment covered, it is one for their doctor: say so, record it in \
questions_for_doctor, and move on.

If they have not collected the prescription yet, say you will check back — \
gently, once. Do not press."""

FIRST_CONTACT_PROMPT = f"{FIRST_CONTACT_FRAMING}\n\n{SHARED_RULES}"

# Days after the consultation within which a call is the first contact rather
# than an interval check-in. Day 0 is the consultation itself; a call placed on
# either day is asking the same day-one questions.
FIRST_CONTACT_MAX_DAY = 1


class CheckInError(RuntimeError):
    """The check-in could not be run or a turn did not match the schema."""


class PatientVoice(Protocol):
    """Whoever is on the other end of the call.

    Real calls implement this over ElevenLabs; tests implement it over a
    script; the CLI implements it over stdin so a developer can be the patient.
    One method, so the turn loop never needs to know which it is talking to.
    """

    def respond(self, agent_said: str) -> str: ...


@dataclass
class TurnDecision:
    """One turn: what the agent decided, said, and heard."""

    data: dict
    raw: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def say(self) -> str:
        return self.data.get("say", "")

    @property
    def reasoning(self) -> str:
        return self.data.get("reasoning", "")

    @property
    def covers(self) -> list[str]:
        return self.data.get("covers", [])

    @property
    def outcomes(self) -> list[dict]:
        return self.data.get("outcomes", [])

    @property
    def symptom_mentions(self) -> list[dict]:
        return self.data.get("symptom_mentions", [])

    @property
    def symptom_scores(self) -> list[dict]:
        return self.data.get("symptom_scores", [])

    @property
    def should_end(self) -> bool:
        return bool(self.data.get("should_end", False))


@dataclass
class CheckIn:
    """A completed call: the check_in.schema.json record, plus provenance.

    `data` is the artifact the brief reads. Everything else is the audit trail
    — the turn-by-turn reasoning, what fired, and how the call ended — kept
    alongside rather than inside it so the stored record stays schema-clean.
    """

    data: dict
    transcript: list[dict] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    # Kept beside `data` rather than in it: check_in.schema.json does not carry
    # symptom mentions, and they must survive the call because the cluster they
    # feed assembles across several. Persisting them is what lets a symptom
    # reported at week 2 still count toward a flag that completes at week 6.
    symptom_mentions: list[dict] = field(default_factory=list)
    # Kept beside `data` for the same reason mentions are, and load-bearing for
    # the same reason: a score is only worth anything next to the ones from
    # earlier calls, so it has to survive this one.
    symptom_scores: list[dict] = field(default_factory=list)
    fired_flags: list[FiredFlag] = field(default_factory=list)
    week: int = 0
    # Days since the consultation, when the call needed finer placement than a
    # week. None for an ordinary interval check-in, where the week is the whole
    # answer and a day would be false precision.
    day: int | None = None
    covered: list[str] = field(default_factory=list)
    ended_because: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def outcomes(self) -> list[dict]:
        return self.data.get("outcomes", [])

    @property
    def is_first_contact(self) -> bool:
        return self.day is not None and self.day <= FIRST_CONTACT_MAX_DAY


@lru_cache(maxsize=1)
def load_schema() -> dict:
    """The turn schema, which is the contract for a single exchange."""
    if not SCHEMA_PATH.is_file():
        raise CheckInError(f"Missing schema at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text())


def turn_schema(context: dict) -> dict:
    """The turn schema with symptom vocabulary bound to this condition.

    Constraining watch_for to an enum built from the context is the single
    highest-leverage line in this module: the model cannot invent a symptom
    category, because the API rejects the response before it reaches us. That
    is what lets redflags.py count mentions and trust the total.
    """
    schema = json.loads(json.dumps(load_schema()))  # deep copy; lru_cache holds the original
    schema.pop("$schema", None)
    schema.pop("$id", None)

    vocabulary = watch_for_vocabulary(context)
    if vocabulary:
        mention = schema["properties"]["symptom_mentions"]["items"]
        mention["properties"]["watch_for"]["enum"] = vocabulary
        mention["properties"]["flag_id"]["enum"] = [
            flag["id"] for flag in context.get("red_flags", [])
        ]
    return schema


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise CheckInError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return anthropic.Anthropic()


def _codex_client() -> openai.OpenAI:
    if not os.environ.get("CODEX_API_KEY"):
        raise CheckInError(
            "CODEX_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return openai.OpenAI(api_key=os.environ["CODEX_API_KEY"], base_url=CODEX_BASE_URL)


def _build_system_prompt(
    facts: IntervalFacts,
    context: dict,
    plan: CheckInPlan | None = None,
    medications: list[Medication] | None = None,
    day: int | None = None,
    series: list[Series] | None = None,
    caretaker: CaretakerContext | None = None,
) -> str:
    """The standing instructions, the person, the interval, the agenda, and the context.

    The context goes in as JSON rather than prose: the agent needs to reason
    over structured fields (ask_from_week, cluster_threshold, links_to) and
    cite ids back in `covers`, and flattening it to prose loses exactly the
    structure that makes that possible.

    The plan is rendered as aims rather than JSON, and deliberately after the
    interval but before the context: it is guidance about what this call is
    for, not a script, and an agent handed a list of sentences reads them out.

    Which framing opens the prompt depends on `day`, because the day-after call
    is a different conversation and not merely an early one. Everything after
    the framing is identical either way.
    """
    prohibited = "\n".join(
        f"- {line}" for line in context.get("safety", {}).get("prohibited_outputs", [])
    )
    framing = context.get("safety", {}).get("framing_rule", "")

    is_first_contact = day is not None and day <= FIRST_CONTACT_MAX_DAY
    standing = FIRST_CONTACT_PROMPT if is_first_contact else SYSTEM_PROMPT

    # Who is being spoken to, before anything about what to ask them. It is
    # first because it governs the whole call rather than any one question —
    # how long to stay, what name to use, what not to press on — and an agent
    # that reads it after the agenda has already decided how the call will go.
    # Omitted entirely for a patient nothing is known about, which is an
    # ordinary call and not a degraded one.
    person = ""
    if caretaker is not None:
        rendered = caretaker_as_agent_brief(caretaker)
        if rendered:
            person = f"=== WHO YOU ARE SPEAKING TO ===\n{rendered}\n\n"

    agenda = ""
    if plan is not None:
        rendered = plan_as_agent_brief(plan, facts.week, day)
        if rendered:
            agenda = (
                f"=== THE AGENDA FOR THIS INTERVAL ===\n{rendered}\n\n"
                "This agenda was set when the appointment was summarised, with "
                "more time than you have on this call. Treat it as informed "
                "judgement about what matters, not as a script — phrase items "
                "yourself, follow what the patient says, and record which item "
                "ids you covered in `covers` so a question nobody reached can "
                "be reported honestly rather than silently dropped.\n\n"
            )

    # Omitted entirely when nothing was prescribed. An agent shown an empty
    # medication section will find something to ask about it, and the brief is
    # explicit that the medication threads simply do not apply to a consultation
    # that prescribed nothing.
    meds = ""
    if medications:
        rendered = medication_as_agent_brief(
            medications, day=day if day is not None else facts.week * 7
        )
        if rendered:
            meds = f"=== THE MEDICATION THREAD ===\n{rendered}\n\n"

    # Placed after the agenda and immediately before the context, so the last
    # thing read before the clinical detail is the instruction that these
    # particular questions are not the agent's to rewrite.
    scored = ""
    if series:
        rendered = trackers_as_agent_brief(series, facts.week)
        if rendered:
            scored = f"=== THE SCORED QUESTIONS ===\n{rendered}\n\n"

    return (
        f"{standing}\n\n"
        f"{person}"
        f"=== THIS INTERVAL ===\n{as_agent_brief(facts)}\n\n"
        f"{meds}"
        f"{agenda}"
        f"{scored}"
        f"=== CLINICAL CONTEXT FOR {facts.condition_name.upper()} ===\n"
        f"{json.dumps(context, indent=2)}\n\n"
        f"=== THE BOUNDARY ===\n{framing}\n\n"
        f"Never produce any of the following:\n{prohibited}"
    )


def _extract(text: str, provider: str) -> dict:
    if not text.strip():
        raise CheckInError(f"{provider} returned an empty turn")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CheckInError(f"Turn was not valid JSON: {exc}. Raw: {text[:500]}") from exc


def _check_turn(data: object) -> dict:
    """Verify the turn has what the loop reads.

    The API enforces the schema, so this guards against a truncated or
    malformed response rather than re-validating field by field.
    """
    if not isinstance(data, dict):
        raise CheckInError(f"Expected a JSON object, got {type(data).__name__}")

    missing = [key for key in load_schema()["required"] if key not in data]
    if missing:
        raise CheckInError(f"Turn is missing required fields: {missing}")
    return data


def run_turn(
    *,
    facts: IntervalFacts,
    context: dict,
    history: list[dict],
    plan: CheckInPlan | None = None,
    medications: list[Medication] | None = None,
    day: int | None = None,
    series: list[Series] | None = None,
    caretaker: CaretakerContext | None = None,
) -> TurnDecision:
    """Ask the agent for its next move.

    Args:
        facts: The interval, from compute_interval_facts.
        context: The disease context the agent reasons over.
        history: Alternating turns so far, as {"role": "assistant"|"user",
            "content": str}. Empty for the opening turn.
        plan: The caretaker's agenda for this interval, if one was made. The
            agent still decides what to ask; this tells it what was judged
            worth asking when there was time to think about it properly.
        medications: The medication thread's current state, if anything was
            prescribed. Omitted or empty switches the whole thread off.
        day: Days since the consultation. Only needed for calls that fall
            inside the first week — chiefly the day-after first contact, which
            week arithmetic alone cannot distinguish from any other week-0 call.
        series: The scored symptoms and whatever they have scored so far. The
            questions are asked verbatim; the prior points are for the agent's
            orientation and are never read back to the patient.
        caretaker: The standing facts about the person — name, when they can
            talk, how much call they can take, what to accommodate. Omitted for
            a patient nothing is known about, which produces an ordinary call.

    Returns:
        A TurnDecision whose `say` has already passed the safety filter.
    """
    system = _build_system_prompt(facts, context, plan, medications, day, series, caretaker)
    schema = turn_schema(context)

    opening = (
        "Start the call. Greet them briefly and ask your first question."
        if day is None or day > FIRST_CONTACT_MAX_DAY
        else (
            "Start the day-after call. Greet them briefly, say why you are "
            "calling, and ask your first question."
        )
    )
    messages = list(history) or [{"role": "user", "content": opening}]

    if PROVIDER == "codex":
        try:
            response = _codex_client().chat.completions.create(
                model=CODEX_MODEL,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "check_in_turn",
                        "schema": schema,
                        "strict": False,
                    },
                },
                messages=[{"role": "system", "content": system}, *messages],
            )
        except openai.APIStatusError as exc:
            raise CheckInError(f"Codex returned {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise CheckInError(f"Could not reach Codex: {exc}") from exc

        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise CheckInError("Codex declined to continue this check-in.")
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
                messages=messages,
            )
        except anthropic.APIStatusError as exc:
            raise CheckInError(f"Claude returned {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise CheckInError(f"Could not reach Claude: {exc}") from exc

        if response.stop_reason == "refusal":
            raise CheckInError("Claude declined to continue this check-in.")
        text = next((b.text for b in response.content if b.type == "text"), "")
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

    data = _check_turn(_extract(text, PROVIDER))

    # The agent has latitude here that a scripted one would not, so what it
    # says is filtered before it is spoken. Fails closed to an acknowledgement
    # rather than raising: a call that dies mid-sentence is worse for the
    # patient than one that says less.
    data["say"] = safety.scrub(data.get("say", ""), context)

    return TurnDecision(data=data, raw=text, usage=usage)


def run_check_in(
    *,
    facts: IntervalFacts,
    context: dict,
    patient: PatientVoice,
    max_turns: int = MAX_TURNS,
    plan: CheckInPlan | None = None,
    medications: list[Medication] | None = None,
    day: int | None = None,
    series: list[Series] | None = None,
    caretaker: CaretakerContext | None = None,
) -> CheckIn:
    """Run a whole call and return the record the brief will read.

    The agent decides what to ask and when it is finished. Two things overrule
    it: the turn cap, and a fired red flag. Flag evaluation happens after every
    turn over mentions accumulated across the entire interval, not just this
    call, because the cluster that matters most builds one symptom at a time
    across calls weeks apart.

    `day` selects the day-after first contact when it is 0 or 1,
    `medications` carries the prescription thread, and `caretaker` carries what
    is known about the person being rung. All three are optional, and an
    interval with none of them behaves exactly as it did before they existed.
    """
    history: list[dict] = []
    transcript: list[dict] = []
    reasoning: list[str] = []
    covered: list[str] = []
    outcomes: dict[str, dict] = {}
    mentions: list[dict] = []
    # Keyed by tracker, so a question asked once produces one point. If the
    # patient revises ("six — no, more like eight"), the later answer is the
    # one they meant, and two points from one call would corrupt a series whose
    # whole meaning is one point per call.
    scores: dict[str, dict] = {}
    questions: list[str] = []
    unprompted: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    ended_because = "agent judged the call complete"

    # Mentions from earlier calls count toward a cluster; seed with them.
    prior_mentions = [
        {
            "watch_for": m.watch_for,
            "flag_id": m.flag_id,
            "patient_words": m.patient_words,
            "week": m.week,
        }
        for m in facts.mentions
    ]

    fired: list[FiredFlag] = []
    tracked_ids = {s.tracker.id for s in series} if series else None

    for turn_index in range(max_turns):
        decision = run_turn(
            facts=facts,
            context=context,
            history=history,
            plan=plan,
            medications=medications,
            day=day,
            series=series,
            caretaker=caretaker,
        )
        usage["input_tokens"] += decision.usage.get("input_tokens", 0)
        usage["output_tokens"] += decision.usage.get("output_tokens", 0)

        transcript.append({"role": "agent", "text": decision.say})
        reasoning.append(decision.reasoning)
        covered.extend(decision.covers)

        for outcome in decision.outcomes:
            cid = outcome.get("commitment_id")
            if cid:
                outcomes[cid] = outcome
        for mention in decision.symptom_mentions:
            mentions.append({**mention, "week": facts.week})
        for score in decision.symptom_scores:
            tracker_id = score.get("tracker_id")
            if not tracker_id:
                continue
            # A tracker the plan does not carry is discarded here rather than
            # downstream, so the stored record only ever contains series the
            # interval actually planned.
            if tracked_ids is not None and tracker_id not in tracked_ids:
                continue
            scores[tracker_id] = {**score, "week": facts.week}
        questions.extend(decision.data.get("questions_for_doctor", []))
        unprompted.extend(decision.data.get("unprompted_reports", []))

        fired = evaluate_flags(context, prior_mentions + mentions, week=facts.week)

        if decision.should_end:
            break

        urgent = [f for f in fired if f.interrupts]
        if urgent:
            # The patient-facing line is copied from the cited context file,
            # never composed here. The agent reads a pre-approved sentence; it
            # does not author a judgement about what the symptoms mean.
            flag = urgent[0]
            warning = f"{flag.patient_facing} {flag.action}".strip()
            transcript.append({"role": "agent", "text": warning})
            ended_because = f"red flag {flag.flag_id} fired ({flag.urgency})"
            break

        patient_said = patient.respond(decision.say)
        transcript.append({"role": "patient", "text": patient_said})
        history = [
            *history,
            {"role": "assistant", "content": decision.raw},
            {"role": "user", "content": patient_said},
        ]
    else:
        ended_because = f"turn cap reached ({max_turns})"

    return CheckIn(
        data={
            "outcomes": list(outcomes.values()),
            "unprompted_reports": unprompted,
            "questions_for_doctor": questions,
        },
        transcript=transcript,
        reasoning=reasoning,
        symptom_mentions=mentions,
        symptom_scores=list(scores.values()),
        fired_flags=fired,
        week=facts.week,
        day=day,
        covered=covered,
        ended_because=ended_because,
        usage=usage,
    )
