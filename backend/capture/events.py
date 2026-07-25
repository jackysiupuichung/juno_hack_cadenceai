"""When things happened, as distinct from when we heard about them.

The rest of the record is organised around conversations: a visit, then check-in
calls at week 2 and week 7. That is a log of Cadence's own activity, and a
patient's interval is not shaped like it. Someone who says "I stopped taking it
after about a fortnight, and the racing started maybe a week after that" has
just described two dated events, neither of which happened on the day of the
call. Recorded against the call date, both collapse onto week 7 and the
sequence between them — the thing a doctor would actually want — is gone.

So events carry two times. `occurred_at` is when the thing happened;
`recorded_at` is when it entered the record. A symptom reported at week 6 that
began at week 2 is a four-week gap, and the gap is often the finding.

Three rules hold this together, all of them about not inventing time:

  - Precision travels with the estimate. "A fortnight ago" becomes a date and a
    `week` precision, never a bare timestamp. A doctor reads a specific date as
    something the patient actually said, so claiming more precision than was
    given is a fabrication even when the midpoint is reasonable.
  - The patient's words are kept. The brief quotes "just after the bank
    holiday" beside the estimate rather than in place of it.
  - Nothing is dated that was not dated. An undated event is stored with
    occurred_at=None rather than guessed at, and the timeline says so.

This module does the arithmetic and the shaping. Deciding what to extract is the
model's job; deciding what is overdue is Python's, for the same reason it always
has been — a due date is a fact about the record, and facts about the record are
not left to a model that will sometimes be wrong about them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# How much slack each precision implies, in days either side of the estimate.
# Used to decide whether an event can be ordered confidently against another:
# two events a day apart, both recorded as "about a fortnight ago", are not
# meaningfully in sequence and the timeline should not imply they are.
PRECISION_SLACK = {
    "exact": 0,
    "day": 0,
    "week": 3,
    "month": 15,
    "approx": 30,
}

# Which event kinds can start a monitoring clock. The disease context hangs its
# schedule off triggers like `treatment_start` and `dose_change`; before events
# existed only the visit date was knowable, so everything else was reported as
# "not scheduled". These are the mappings that let a real event anchor a real
# due date.
ANCHOR_KINDS = {
    "treatment_start": ("medication_start",),
    "dose_change": ("dose_change",),
    "last_result": ("test_result",),
}

SCHEDULABLE = frozenset({"test_taken", "appointment", "test_result"})


@dataclass(frozen=True)
class Event:
    """One dated thing, and how well it is dated."""

    kind: str
    label: str
    occurred_at: date | None = None
    precision: str = "day"
    source: str = "patient_reported"
    patient_words: str = ""
    due_at: date | None = None
    context_ids: tuple[str, ...] = ()
    detail: str = ""
    event_id: str = ""
    recorded_at: date | None = None

    @property
    def is_scheduled(self) -> bool:
        """A due date nobody has met yet."""
        return self.occurred_at is None and self.due_at is not None

    @property
    def is_dated(self) -> bool:
        return self.occurred_at is not None

    @property
    def slack_days(self) -> int:
        return PRECISION_SLACK.get(self.precision, 0)

    @property
    def reporting_delay_days(self) -> int | None:
        """How long between the thing happening and Cadence hearing about it.

        None when either end is unknown. A large delay is not a fault — it is
        how chronic illness is actually reported — but it is worth surfacing,
        because a symptom that started a month before anyone asked says
        something about the interval that the symptom alone does not.
        """
        if self.occurred_at is None or self.recorded_at is None:
            return None
        return max(0, (self.recorded_at - self.occurred_at).days)

    def when(self) -> str:
        """The timing as a phrase honest about its own precision.

        The patient's words win when we have them, because they are the only
        part of this that is not an inference.
        """
        if self.occurred_at is None:
            return self.patient_words or "date not established"

        stamp = self.occurred_at.isoformat()
        if self.precision in ("exact", "day"):
            base = stamp
        elif self.precision == "week":
            base = f"around {stamp} (within about a week)"
        elif self.precision == "month":
            base = f"around {stamp} (within about a month)"
        else:
            base = f"roughly {stamp}"

        if self.patient_words:
            return f'{base} — patient\'s words: "{self.patient_words}"'
        return base


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def from_row(row: dict) -> Event:
    """An Event from a persisted `events` row."""
    return Event(
        kind=row.get("kind", "other"),
        label=row.get("label", ""),
        occurred_at=_parse_date(row.get("occurred_at")),
        precision=row.get("precision", "day"),
        source=row.get("source", "patient_reported"),
        patient_words=row.get("patient_words", ""),
        due_at=_parse_date(row.get("due_at")),
        context_ids=tuple(row.get("context_ids") or ()),
        detail=(row.get("detail") or {}).get("detail", "")
        if isinstance(row.get("detail"), dict)
        else str(row.get("detail") or ""),
        event_id=row.get("id", ""),
        recorded_at=_parse_date(row.get("recorded_at")),
    )


def from_extraction(
    item: dict, *, conversation_date: date, source: str, context_ids=()
) -> Event | None:
    """An Event from one entry of an event.schema.json extraction.

    Returns None for an entry with no usable kind or label, rather than storing
    a row that would appear on a timeline saying nothing.
    """
    kind = (item.get("kind") or "").strip()
    label = (item.get("label") or "").strip()
    if not kind or not label:
        return None

    occurred = _parse_date(item.get("occurred_at"))
    # A date after the conversation that reported it is a model error, not a
    # prediction. Clamping rather than dropping keeps the event, which is still
    # a real thing that happened, while refusing the impossible timestamp.
    if occurred and occurred > conversation_date:
        occurred = conversation_date

    return Event(
        kind=kind,
        label=label,
        occurred_at=occurred,
        precision=item.get("precision") or "day",
        source=source,
        patient_words=item.get("patient_words", ""),
        context_ids=tuple(item.get("context_ids") or context_ids),
        detail=item.get("detail", ""),
        recorded_at=conversation_date,
    )


def to_row(event: Event, *, condition_id: str, **links) -> dict:
    """The `events` row for one Event. `links` carries visit_id/check_in_id."""
    row = {
        "condition_id": condition_id,
        "kind": event.kind,
        "label": event.label,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "due_at": event.due_at.isoformat() if event.due_at else None,
        "precision": event.precision,
        "source": event.source,
        "patient_words": event.patient_words,
        "context_ids": list(event.context_ids),
        "detail": {"detail": event.detail} if event.detail else {},
    }
    row.update({k: v for k, v in links.items() if v})
    return row


def anchors(events: list[Event]) -> dict[str, date]:
    """The latest date for each monitoring trigger the record can evidence.

    The disease context schedules against triggers — `treatment_start`,
    `dose_change`, `last_result` — and until events existed only the visit date
    was knowable, so everything else was reported as "not scheduled". Latest
    rather than earliest because a second dose change restarts the clock: the
    test is due seven weeks after the most recent change, not the first.
    """
    found: dict[str, date] = {}
    for trigger, kinds in ANCHOR_KINDS.items():
        dated = [e.occurred_at for e in events if e.kind in kinds and e.occurred_at]
        if dated:
            found[trigger] = max(dated)
    return found


def timeline(events: list[Event]) -> list[Event]:
    """What has happened, in order, with undated events last.

    Scheduled events are excluded: a blood test due next week has not happened,
    and listing it as history — or worse, as history with no date — would put a
    thing that never occurred into the account of the interval. They belong to
    `upcoming` and `overdue`, which say plainly that they are still owed.

    Undated events that DID happen are kept rather than dropped. "They stopped
    taking it at some point and could not say when" is a real finding, and an
    interval that silently omits it looks tidier than it was.
    """
    happened = [e for e in events if not e.is_scheduled]
    dated = sorted((e for e in happened if e.is_dated), key=lambda e: e.occurred_at)
    return [*dated, *(e for e in happened if not e.is_dated)]


def upcoming(events: list[Event], *, today: date, within_days: int = 90) -> list[Event]:
    """Scheduled events still ahead, soonest first."""
    horizon = today + timedelta(days=within_days)
    return sorted(
        (e for e in events if e.is_scheduled and e.due_at and today <= e.due_at <= horizon),
        key=lambda e: e.due_at,
    )


def overdue(events: list[Event], *, today: date, grace_days: int = 0) -> list[Event]:
    """Scheduled events whose date has passed with nothing recorded against them.

    `fulfilled_by` is resolved before this is called, so anything still here is
    genuinely outstanding rather than merely un-linked.
    """
    return sorted(
        (
            e
            for e in events
            if e.is_scheduled and e.due_at and (today - e.due_at).days > grace_days
        ),
        key=lambda e: e.due_at,
    )


def observations(events: list[Event], *, today: date) -> list[str]:
    """Factual, dated statements about the chronology — never a conclusion.

    Written here rather than by the brief's model for the same reason every
    other observation is: this is where clinical decision support starts. "The
    repeat blood test was due on 12 August and nothing has been recorded" is a
    fact about the record. "The dose is probably wrong" is a diagnosis. Writing
    the factual form in Python and handing it over as a line to reproduce
    verbatim means the model never gets the chance to produce the second kind.
    """
    lines = []

    for event in overdue(events, today=today):
        days = (today - event.due_at).days
        weeks = days // 7
        span = (
            f"{weeks} week{'s' if weeks != 1 else ''}"
            if weeks >= 1
            else f"{days} day{'s' if days != 1 else ''}"
        )
        lines.append(
            f"{event.label} was due on {event.due_at.isoformat()} and has not "
            f"been recorded as done — that is {span} ago."
        )

    # A long gap between something happening and anyone hearing about it is
    # stated plainly, without suggesting what it means. It is reported only for
    # symptoms, where the delay changes how the interval reads; a test taken
    # three weeks before it was mentioned is unremarkable.
    for event in events:
        if event.kind != "symptom_onset":
            continue
        delay = event.reporting_delay_days
        if delay is not None and delay >= 14:
            lines.append(
                f"{event.label} was first reported {delay // 7} weeks after it "
                f"began ({event.when()})."
            )

    undated = [e for e in events if not e.is_dated and e.source == "patient_reported"]
    for event in undated:
        lines.append(f"{event.label}: reported, but not placed in time.")

    return lines


def as_agent_brief(events: list[Event], *, today: date) -> str:
    """The chronology rendered for a system prompt.

    Ordered prose rather than JSON: the agent reads this alongside the interval
    facts and the disease context, and a nested structure makes the one thing
    that matters here — the sequence — harder to hold onto.
    """
    dated = timeline(events)
    if not dated:
        return ""

    lines = ["Chronology of this interval:"]
    for event in dated:
        if event.is_scheduled:
            continue
        lines.append(f"  {event.when()} — {event.label}")

    soon = upcoming(events, today=today)
    if soon:
        lines.append("\nComing up:")
        for event in soon:
            lines.append(f"  {event.due_at.isoformat()} — {event.label}")

    late = overdue(events, today=today)
    if late:
        lines.append("\nDue and not yet recorded as done:")
        for event in late:
            lines.append(f"  {event.due_at.isoformat()} — {event.label}")

    return "\n".join(lines)
