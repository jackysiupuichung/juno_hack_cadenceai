"""The facts about an interval, assembled for an agent to reason over.

A consultation opens an interval. Two things describe it: the transcript (what
this particular patient agreed to) and the disease context (what the guideline
says the weeks after this treatment usually look like). This module gathers
both into one brief the check-in agent reads before deciding what to ask.

It deliberately does NOT decide what to ask. That judgement belongs to the
agent, which sees the whole context file — every probe, every red flag, the
expected trajectory, the monitoring schedule — and works out its own line of
questioning, including threads the file's authors never anticipated.

What stays here is the arithmetic and the bookkeeping the agent should not have
to re-derive and would sometimes get wrong: how many weeks have elapsed, what
each commitment's latest status is across several prior calls, and which
symptoms have already been mentioned and when. Facts, computed once, stated
plainly. The agent reasons; this module remembers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

CONTEXT_DIR = Path(__file__).resolve().parents[2] / "fixtures"

DEFAULT_CONDITION = "hypothyroidism"

# A commitment is still worth raising while it is in one of these states.
# "done" and "changed" are settled; re-asking spends a question on a patient
# whose scarcest resource is attention.
OPEN_STATUSES = frozenset({"unknown", "not_done", "partial"})

# Monitoring events hang off a clock that some event starts. Only
# treatment_start is knowable from a single visit — the others need a second
# visit or a lab result a one-interval record does not have. Rather than invent
# an anchor, those events are reported as unscheduled; see _monitoring_facts.
ANCHOR_TRIGGERS = frozenset({"treatment_start"})


class IntervalError(RuntimeError):
    """The interval could not be assembled from the inputs given."""


@lru_cache(maxsize=4)
def load_context(condition_id: str = DEFAULT_CONDITION) -> dict:
    """The curated clinical context for one condition.

    Cached because it is read once per check-in and once per brief, and never
    changes at runtime — it is a file a human wrote and cited.
    """
    path = CONTEXT_DIR / f"{condition_id}.context.json"
    if not path.is_file():
        raise IntervalError(f"No disease context for {condition_id!r} at {path}")

    context = json.loads(path.read_text())
    missing = [
        key
        for key in ("condition", "red_flags", "trajectory", "monitoring",
                    "check_in_probes", "safety")
        if key not in context
    ]
    if missing:
        raise IntervalError(f"Disease context {condition_id!r} is missing: {missing}")
    return context


def watch_for_vocabulary(context: dict) -> list[str]:
    """Every canonical symptom phrase in this context, deduped and ordered.

    The check-in schema constrains symptom_mentions to this list, so the model
    can only report a symptom the context actually names. That is what makes
    the cluster count in redflags.py trustworthy: a hallucinated phrase cannot
    reach the counter, because the API rejects it before it gets there.
    """
    seen: dict[str, None] = {}
    for flag in context.get("red_flags", []):
        for phrase in flag.get("watch_for", []):
            seen.setdefault(phrase, None)
    return list(seen)


def commitment_id(index: int) -> str:
    """The stable id for the nth commitment in a visit summary.

    visit_summary.schema.json has no id field, but check_in and brief both key
    on one. Deriving it positionally keeps the three consistent without
    regenerating the summary fixture — a visit's commitments list is ordered
    and append-only, so position is stable for the interval's lifetime.
    Persisted rows use the database id instead; this is the offline equivalent.
    """
    return f"c{index + 1}"


@dataclass(frozen=True)
class CommitmentFact:
    """Something agreed at the visit, and where it currently stands."""

    commitment_id: str
    text: str
    type: str
    timeframe: str
    status: str
    last_asked_week: int | None
    source_quote: str = ""

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


@dataclass(frozen=True)
class MonitoringFact:
    """A scheduled clinical event and where the interval sits relative to it."""

    event: dict
    due_week: int | None      # None when no anchor exists in the record
    weeks_overdue: int        # 0 unless past due_week + the grace period
    anchor: str               # what the clock hung on, or why it did not start


@dataclass(frozen=True)
class TrajectoryFact:
    """A milestone the guideline expects, and where the interval sits on it.

    Held separately from MonitoringFact because the two answer different
    questions. Monitoring is about appointments that were meant to be kept —
    something a patient can be behind on. A trajectory marker is about how the
    body has responded, which nobody is behind on. That distinction is the
    reason `status` is a window position and never a verdict.
    """

    event: dict
    status: str               # too_early | in_window | past_expected
    weeks_past_expected: int  # 0 unless week > expected_by_week


@dataclass(frozen=True)
class SymptomMention:
    """A canonical symptom phrase the patient reported, and when."""

    watch_for: str
    flag_id: str
    patient_words: str
    week: int


@dataclass(frozen=True)
class IntervalFacts:
    """What is true about this interval as of `today`.

    Handed to the check-in agent alongside the full disease context. Nothing
    here is a decision — these are the things that are tedious to recompute and
    easy to get subtly wrong, stated once so the agent can spend its attention
    on the conversation instead.
    """

    condition_id: str
    condition_name: str
    plain_name: str
    visit_date: date
    today: date
    week: int
    commitments: list[CommitmentFact] = field(default_factory=list)
    monitoring: list[MonitoringFact] = field(default_factory=list)
    trajectory: list[TrajectoryFact] = field(default_factory=list)
    mentions: list[SymptomMention] = field(default_factory=list)
    unanswered_questions: list[str] = field(default_factory=list)
    previous_check_in_weeks: list[int] = field(default_factory=list)

    # Cross-visit context. Optional, and absent for the first interval a patient
    # ever records — which is the common case and must stay the cheap one. When
    # present, it is what makes the second consultation start warm rather than
    # cold: the interval knows it is not the first.
    previous_brief: dict | None = None
    prior_visit_dates: list[date] = field(default_factory=list)

    @property
    def open_commitments(self) -> list[CommitmentFact]:
        return [c for c in self.commitments if c.is_open]

    @property
    def settled_commitments(self) -> list[CommitmentFact]:
        return [c for c in self.commitments if not c.is_open]

    @property
    def is_first_check_in(self) -> bool:
        return not self.previous_check_in_weeks


def _weeks_between(start: date, end: date) -> int:
    """Whole weeks elapsed, floored, never negative.

    A check-in dated before its visit is a data error upstream, but it must not
    produce a negative week that makes the whole interval look like it has not
    started. Clamping to 0 fails visibly instead.
    """
    return max(0, (end - start).days // 7)


def _commitment_facts(summary: dict, prior_check_ins: list[dict]) -> list[CommitmentFact]:
    """Every commitment from the visit, with its latest known status.

    Status comes from the most recent check-in that actually addressed it.
    Check-ins are applied oldest-first, so a commitment reported "not_done" at
    week 2 and "done" at week 6 ends up done.
    """
    latest: dict[str, tuple[str, int | None]] = {}
    for check_in in prior_check_ins:
        week = check_in.get("week")
        for outcome in check_in.get("outcomes", []):
            cid = outcome.get("commitment_id")
            if not cid:
                continue
            status = outcome.get("status", "unknown")
            # "unknown" means the commitment was not discussed on that call. It
            # records that we were in touch, but must not overwrite a real
            # answer given on an earlier one.
            if status == "unknown" and cid in latest:
                latest[cid] = (latest[cid][0], week)
            else:
                latest[cid] = (status, week)

    facts = []
    for i, commitment in enumerate(summary.get("commitments", [])):
        cid = commitment_id(i)
        status, last_week = latest.get(cid, ("unknown", None))

        # Two id schemes meet here. Offline, commitments are keyed positionally
        # (c1, c2…) and their status is derived from check-in JSON above.
        # Persisted, they carry Supabase UUIDs and the database has already
        # resolved the status — so the outcome ids never match the positional
        # ones and everything falls through to "unknown". A stored status is
        # therefore authoritative when present: it is the answer the patient
        # actually gave, and treating it as absent made the brief report
        # "never discussed in a check-in" about commitments it had, on the same
        # page, just quoted the patient answering.
        stored = commitment.get("status")
        if stored and stored != "pending":
            status = stored
            if last_week is None and prior_check_ins:
                last_week = prior_check_ins[-1].get("week")

        facts.append(
            CommitmentFact(
                commitment_id=commitment.get("id") or cid,
                text=commitment.get("text", ""),
                type=commitment.get("type", ""),
                timeframe=commitment.get("timeframe", ""),
                status=status,
                last_asked_week=last_week,
                source_quote=commitment.get("source_quote", ""),
            )
        )
    return facts


def _monitoring_facts(context: dict, visit_date: date, week: int) -> list[MonitoringFact]:
    """Where the interval sits against each scheduled clinical event.

    Events whose clock never started are reported with due_week=None and an
    anchor line saying why, rather than omitted. The agent should be able to
    see that a three-monthly blood test exists but is not yet scheduled — that
    is different from it not existing, and the difference matters to the brief.
    """
    facts = []
    for event in context.get("monitoring", []):
        trigger = event.get("trigger")
        if trigger not in ANCHOR_TRIGGERS:
            facts.append(
                MonitoringFact(
                    event=event,
                    due_week=None,
                    weeks_overdue=0,
                    anchor=f"not scheduled — no {trigger} recorded in this interval",
                )
            )
            continue

        due_week = int(event.get("interval_weeks", 0))
        grace = event.get("overdue_after_weeks", 0)
        past_due = week - due_week
        facts.append(
            MonitoringFact(
                event=event,
                due_week=due_week,
                weeks_overdue=past_due if past_due > grace else 0,
                anchor=f"{trigger} {visit_date.isoformat()}",
            )
        )

    return facts


def _trajectory_facts(context: dict, week: int) -> list[TrajectoryFact]:
    """Where the interval sits against each expected-course milestone.

    Every marker is reported, including the ones that are still too early, for
    the same reason _monitoring_facts reports unscheduled events: the agent
    needs to know a marker exists and is not yet in play. Otherwise "nothing to
    say about symptom resolution at week 4" is indistinguishable from "there is
    no such milestone", and only the first is true.
    """
    facts = []
    for event in context.get("trajectory", []):
        earliest = int(event.get("earliest_week", 0))
        expected_by = int(event.get("expected_by_week", earliest))

        if week < earliest:
            status, past = "too_early", 0
        elif week <= expected_by:
            status, past = "in_window", 0
        else:
            status, past = "past_expected", week - expected_by

        facts.append(TrajectoryFact(event=event, status=status, weeks_past_expected=past))
    return facts


def _mentions(prior_check_ins: list[dict]) -> list[SymptomMention]:
    """Canonical symptom phrases already reported, across every prior call.

    Kept as a flat list with weeks attached because the pattern that matters —
    the over-replacement cluster — accumulates one symptom at a time across
    calls weeks apart, and is invisible to anything that only looks at one.
    """
    out = []
    for check_in in prior_check_ins:
        week = check_in.get("week", 0)
        for mention in check_in.get("symptom_mentions", []):
            out.append(
                SymptomMention(
                    watch_for=mention.get("watch_for", ""),
                    flag_id=mention.get("flag_id", ""),
                    patient_words=mention.get("patient_words", ""),
                    week=mention.get("week", week),
                )
            )
    return out


def compute_interval_facts(
    *,
    summary: dict,
    context: dict,
    visit_date: date,
    today: date,
    prior_check_ins: list[dict] = (),
    previous_brief: dict | None = None,
    prior_visit_dates: list[date] = (),
) -> IntervalFacts:
    """Assemble everything true about this interval as of `today`.

    Args:
        summary: A visit summary conforming to visit_summary.schema.json.
        context: A disease context, from `load_context`.
        visit_date: When the consultation happened — the clock's origin.
        today: The date to evaluate against.
        prior_check_ins: Earlier check-in records, oldest first. Each is a
            check_in.schema.json body plus `week` and `symptom_mentions`.
        previous_brief: The brief produced at the end of the previous interval,
            conforming to brief.schema.json. Optional, and defaulted so that
            every caller written before the loop closed keeps working.
        prior_visit_dates: Consultations before this one, oldest first.

    Returns:
        IntervalFacts. Every field is computed from the inputs; none is a
        judgement about what to do next.
    """
    prior = list(prior_check_ins)
    condition = context["condition"]
    week = _weeks_between(visit_date, today)

    return IntervalFacts(
        condition_id=condition["id"],
        condition_name=condition.get("name", ""),
        plain_name=condition.get("plain_name", ""),
        visit_date=visit_date,
        today=today,
        week=week,
        commitments=_commitment_facts(summary, prior),
        monitoring=_monitoring_facts(context, visit_date, week),
        trajectory=_trajectory_facts(context, week),
        mentions=_mentions(prior),
        unanswered_questions=[
            question
            for check_in in prior
            for question in check_in.get("questions_for_doctor", [])
        ],
        previous_check_in_weeks=[c.get("week", 0) for c in prior],
        previous_brief=previous_brief,
        prior_visit_dates=list(prior_visit_dates),
    )


def as_agent_brief(facts: IntervalFacts) -> str:
    """The facts, rendered for a system prompt.

    Plain prose rather than JSON because the agent reads this alongside the
    disease context and reasons over both; a wall of nested objects makes the
    salient things (week number, what is still open) harder to hold onto.
    """
    lines = [
        f"Condition: {facts.condition_name} ({facts.plain_name})",
        f"Visit date: {facts.visit_date.isoformat()}",
        f"Today: {facts.today.isoformat()} — week {facts.week} of this interval.",
    ]

    if facts.previous_check_in_weeks:
        weeks = ", ".join(f"week {w}" for w in facts.previous_check_in_weeks)
        lines.append(f"Previous check-ins: {weeks}.")
    else:
        lines.append("This is the first check-in of the interval.")

    lines.append("\nWhat was agreed at the visit:")
    for c in facts.commitments:
        when = f", last discussed week {c.last_asked_week}" if c.last_asked_week is not None else ""
        lines.append(f"  [{c.commitment_id}] {c.text} (status: {c.status}{when})")

    if facts.mentions:
        lines.append("\nSymptoms already reported this interval:")
        for m in facts.mentions:
            lines.append(f"  week {m.week}: {m.watch_for} — \"{m.patient_words}\"")

    lines.append("\nScheduled clinical events:")
    for m in facts.monitoring:
        if m.due_week is None:
            lines.append(f"  {m.event['event']}: {m.anchor}")
        elif m.weeks_overdue:
            lines.append(
                f"  {m.event['event']}: due week {m.due_week}, "
                f"{m.weeks_overdue} week(s) past the grace period"
            )
        else:
            lines.append(f"  {m.event['event']}: due week {m.due_week}")

    if facts.trajectory:
        lines.append("\nExpected course:")
        for t in facts.trajectory:
            marker = t.event.get("marker", t.event.get("id", ""))
            window = f"weeks {t.event.get('earliest_week')}–{t.event.get('expected_by_week')}"
            if t.status == "too_early":
                where = f"not yet expected ({window})"
            elif t.status == "in_window":
                where = f"inside the usual window ({window})"
            else:
                where = (
                    f"past the usual window ({window}), "
                    f"{t.weeks_past_expected} week(s) beyond it"
                )
            lines.append(f"  {marker}: {where} — {t.event.get('expectation', '')}")

    if facts.unanswered_questions:
        lines.append("\nQuestions the patient has raised for their doctor:")
        lines.extend(f"  - {q}" for q in facts.unanswered_questions)

    if facts.previous_brief:
        # Deliberately three lines, not a JSON dump. The agent is already
        # holding the whole disease context and this interval's facts; the job
        # of this section is only to stop the call opening as though the
        # patient had never been through any of this before.
        lines.append("\nThis is not their first interval.")
        if facts.prior_visit_dates:
            dates = ", ".join(d.isoformat() for d in facts.prior_visit_dates)
            lines.append(f"  Earlier consultations: {dates}.")

        changed = facts.previous_brief.get("changed", [])
        if changed:
            deltas = "; ".join(
                f"{c.get('text', '')} ({c.get('direction', '')})" for c in changed[:3]
            )
            lines.append(f"  By the end of the last interval: {deltas}.")

        unresolved = [
            d.get("text", "")
            for d in facts.previous_brief.get("did", [])
            if d.get("status") in {"not_done", "partial"}
        ]
        if unresolved:
            lines.append(
                f"  Left unfinished last time: {'; '.join(unresolved[:3])}."
            )

        carried = facts.previous_brief.get("open_questions", [])
        if carried:
            lines.append(f"  They were still asking: {'; '.join(carried[:2])}.")

    return "\n".join(lines)


def observations(facts: IntervalFacts) -> list[str]:
    """Factual, dated statements about the interval — no conclusions.

    Written here rather than by the brief's model, because this is precisely
    where clinical decision support starts. "Your doctor asked for repeat
    bloods around week 7; that was three weeks ago" is a fact about the record.
    "Your dose may be too high" is a diagnosis. Composing the factual form in
    Python and handing it to the model as a line to reproduce verbatim means
    the model never has the opportunity to produce the second kind.
    """
    lines = []

    for m in facts.monitoring:
        if m.due_week is None:
            continue
        if m.weeks_overdue:
            lines.append(
                f"{m.event['event']} was due around week {m.due_week} and has not "
                f"been recorded as done — that is {m.weeks_overdue} "
                f"week{'s' if m.weeks_overdue != 1 else ''} past the usual window."
            )
        elif facts.week >= m.due_week:
            lines.append(f"{m.event['event']} is due around now (week {m.due_week}).")

    # The context's own `if_not_met` wording is reproduced verbatim rather than
    # paraphrased, and the sentence is completed with nothing but two dates.
    # A missed window here is ordinary — the guideline's ranges are wide, and
    # people fall outside them for reasons that have nothing to do with the
    # treatment. Anything that reads as a conclusion ("not responding", "the
    # dose may be wrong") is both a diagnosis we are not permitted to make and,
    # far more often than not, simply false. safety.prohibited_outputs names
    # this exact failure: framing an expected-window shortfall as something
    # being wrong. So the line states the record and stops.
    for t in facts.trajectory:
        if t.status == "past_expected":
            # The context authors wrote if_not_met as a standalone sentence, so
            # its full stop is trimmed before the clause that dates it.
            marker = t.event.get("if_not_met", "").rstrip(". ")
            if marker:
                lines.append(
                    f"{marker} — the usual window for this is by week "
                    f"{t.event.get('expected_by_week')}, and it is now week {facts.week}."
                )

    for c in facts.commitments:
        if c.status == "not_done":
            lines.append(f"Not done: {c.text}")
        elif c.status == "unknown" and c.last_asked_week is None:
            lines.append(f"Never discussed in a check-in: {c.text}")

    return [line for line in lines if line]
