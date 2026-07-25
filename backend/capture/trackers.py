"""Scored symptoms: the same question, asked the same way, call after call.

Most of what a check-in records is categorical — the test happened or it did
not, the symptom was mentioned or it was not. That is enough to say what
occurred and not enough to say which way it is going. "Better, worse, or about
the same" is the existing probe's honest attempt at a direction, and it fails
across an interval for the reason all such questions fail: it is answered
relative to a remembered baseline that drifts, so three "about the same"s in a
row can describe a slow decline.

A number fixes that, but only if the question is genuinely identical every time.
A 1-10 score is comparable to last month's score when the wording, the scale and
the anchors are the same; reword it and the series silently stops meaning
anything, because the patient is now answering a different question. So the
tracked set is decided once by the planner, frozen into the plan, and reproduced
verbatim on every call. This is the one place in the codebase where the agent
does NOT phrase things itself, and the exception is the whole point.

The scale is fixed for the same reason: 1 is none or best, 10 is the worst it
has been, on every tracker of every condition. A per-tracker direction would be
richer and would mean every reader of a series has to check which way this
particular one runs before reading it — and a doctor with two minutes will not.
One direction, always: rising is worse.

What this module does not do is say what a series means. It computes the delta
between the first and last score because that is subtraction; it renders a
sparkline because that is formatting. Whether a four-point rise matters, whether
it is the drug, whether anything should change — none of that is here, and the
`observations` output is worded so a model reading it downstream cannot mistake
a trend for a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCALE_MIN = 1
SCALE_MAX = 10

# How the scale is described to the patient, every time. Part of the question's
# identity: a score given against "10 is unbearable" is not comparable with one
# given against "10 is the worst it's been", so the anchor text is frozen
# alongside the wording rather than left to the agent.
SCALE_ANCHOR = f"{SCALE_MIN} is not at all and {SCALE_MAX} is the worst it has been"

# A series needs two real scores before the word "change" applies to it. One
# score is a baseline; zero is a question nobody answered.
MIN_POINTS_FOR_TREND = 2

# Below this, a delta is noise in how someone happens to feel on the morning
# they were phoned rather than a movement worth putting in front of a doctor.
# Deliberately conservative: a brief that flags every wobble trains its reader
# to skim, which costs more than the wobbles are worth.
MEANINGFUL_DELTA = 2


@dataclass(frozen=True)
class Tracker:
    """One scored symptom, fixed for the interval.

    `question` is reproduced verbatim on every call — it is the only text in
    this system the agent is told to read out rather than phrase itself. The
    fields around it exist to make that reproduction checkable: `id` keys the
    series, `context_id` records what in the disease context justified tracking
    this at all, and `from_consultation` records whether the patient actually
    raised it.
    """

    id: str
    label: str            # short name for a chart axis or a brief line
    question: str         # asked verbatim, every call
    context_id: str = ""  # the probe / trajectory / red_flag this derives from
    from_consultation: bool = False

    def asked(self) -> str:
        """The question as it goes to the patient, anchors included.

        The anchor is appended here rather than stored in `question` so it
        cannot drift between trackers, and so a planner that forgets to mention
        the scale still produces a comparable series.
        """
        if str(SCALE_MAX) in self.question and str(SCALE_MIN) in self.question:
            return self.question
        return f"{self.question} — where {SCALE_ANCHOR}."


@dataclass(frozen=True)
class Score:
    """One answer, on one call.

    A `Score` with `value=None` is a call where the question was asked and no
    number came back. That is a real and common outcome — "I don't know",
    "about the same, I suppose" — and it is recorded rather than dropped,
    because "asked, no number" and "never asked" are different facts and only
    one of them is a gap in the questioning.
    """

    tracker_id: str
    week: int
    value: int | None
    patient_words: str = ""

    @property
    def is_scored(self) -> bool:
        return self.value is not None


@dataclass
class Series:
    """Every score for one tracker across the interval, oldest first."""

    tracker: Tracker
    scores: list[Score] = field(default_factory=list)

    @property
    def points(self) -> list[Score]:
        """Only the calls that produced a number."""
        return [s for s in self.scores if s.is_scored]

    @property
    def first(self) -> Score | None:
        return self.points[0] if self.points else None

    @property
    def last(self) -> Score | None:
        return self.points[-1] if self.points else None

    @property
    def unscored_weeks(self) -> list[int]:
        """Calls that asked and got no number — the honest gaps in the series."""
        return [s.week for s in self.scores if not s.is_scored]

    @property
    def delta(self) -> int | None:
        """Last minus first, or None when there is not enough to subtract.

        Positive is worse, because the scale runs that way on every tracker.
        """
        if len(self.points) < MIN_POINTS_FOR_TREND:
            return None
        return self.last.value - self.first.value

    @property
    def direction(self) -> str:
        """Which way the series has moved: better | worse | steady | unknown.

        "steady" is a claim about the numbers only — it means the endpoints are
        within the noise band, not that nothing happened in between and
        certainly not that the patient is stable. `observations` never uses the
        word for that reason.
        """
        delta = self.delta
        if delta is None:
            return "unknown"
        if delta <= -MEANINGFUL_DELTA:
            return "better"
        if delta >= MEANINGFUL_DELTA:
            return "worse"
        return "steady"

    def sparkline(self) -> str:
        """The series as one line: "wk1 6 → wk3 4 → wk7 3".

        Weeks are carried on every point rather than implied by position,
        because the calls are not evenly spaced and a reader who assumes they
        are will misread the slope.
        """
        return " → ".join(f"wk{s.week} {s.value}" for s in self.points)


def from_plan(plan_data: dict) -> list[Tracker]:
    """The trackers the planner froze for this interval."""
    return [
        Tracker(
            id=row["id"],
            label=row.get("label", row["id"]),
            question=row["question"],
            context_id=row.get("context_id", ""),
            from_consultation=bool(row.get("from_consultation", False)),
        )
        for row in plan_data.get("tracked_symptoms", [])
    ]


def collect(trackers: list[Tracker], check_ins: list[dict]) -> list[Series]:
    """Assemble each tracker's series from every check-in of the interval.

    Scores are keyed by tracker id, so a check-in that reported a score for
    something no longer tracked is ignored rather than creating a stray series —
    the tracked set is the plan's to decide, and a series nobody planned is not
    one a brief should show.

    Check-ins are taken in the order given, which is oldest-first everywhere
    else in this codebase; a score's own `week` is preferred over the call's so
    a record assembled out of order still sorts correctly.
    """
    by_id = {t.id: Series(tracker=t) for t in trackers}

    for check_in in check_ins:
        call_week = check_in.get("week") or (check_in.get("_meta") or {}).get("week") or 0
        for row in check_in.get("symptom_scores", []) or []:
            series = by_id.get(row.get("tracker_id"))
            if series is None:
                continue
            value = row.get("value")
            series.scores.append(
                Score(
                    tracker_id=row["tracker_id"],
                    week=row.get("week", call_week),
                    value=int(value) if isinstance(value, (int, float)) else None,
                    patient_words=row.get("patient_words", ""),
                )
            )

    for series in by_id.values():
        series.scores.sort(key=lambda s: s.week)
    return list(by_id.values())


def as_agent_brief(series: list[Series], week: int) -> str:
    """The trackers rendered for a check-in agent's system prompt.

    The instruction to reproduce the wording verbatim is attached to the
    questions themselves rather than left in the standing prompt, because this
    is the one instruction in the system that contradicts everything else the
    agent is told about phrasing. Put it anywhere else and it loses.

    Prior scores are shown so the agent knows a baseline exists — but never as
    something to read back to the patient, since telling someone they said six
    last time is how you get six again.
    """
    if not series:
        return ""

    lines = [
        "Ask each of these once, worded EXACTLY as written. This is the only "
        "place you must not phrase things yourself: these scores are compared "
        "with the ones from earlier calls, and a reworded question produces a "
        "number that cannot be compared. Do not read the earlier scores back to "
        "them — an anchored patient repeats their last answer.",
    ]

    for s in series:
        lines.append(f'  [{s.tracker.id}] "{s.tracker.asked()}"')
        if s.points:
            lines.append(f"      so far: {s.sparkline()} (for your reference only)")
        else:
            lines.append("      no score recorded yet this interval")

    lines.append(
        "\nRecord each answer in symptom_scores. If they will not give a number, "
        "record the tracker with value null and put what they actually said in "
        "patient_words — a made-up number is worse than a gap, and pressing for "
        "one is worse than either."
    )
    return "\n".join(lines)


def observations(series: list[Series]) -> list[str]:
    """Factual statements about each series, for the brief.

    Same contract as interval.observations and medication.observations: these
    are lines a model reproduces verbatim, so they state the numbers and the
    weeks and stop. The wording is chosen to be hard to turn into a finding —
    "reported X at week 1 and Y at week 7" invites no conclusion, where "worsened
    by four points" invites exactly one, and the conclusion is the doctor's.
    """
    lines = []
    for s in series:
        label = s.tracker.label

        if not s.points:
            if s.scores:
                lines.append(
                    f"{label} was asked about but no rating was given "
                    f"({len(s.scores)} call(s))."
                )
            else:
                lines.append(f"{label} was never rated during this interval.")
            continue

        if len(s.points) < MIN_POINTS_FOR_TREND:
            point = s.points[0]
            lines.append(
                f"{label} was rated {point.value} out of {SCALE_MAX} at week "
                f"{point.week}. Only one rating was given, so there is nothing "
                "to compare it with."
            )
            continue

        first, last = s.first, s.last
        lines.append(
            f"{label}, self-rated out of {SCALE_MAX} where {SCALE_MAX} is worst: "
            f"{s.sparkline()}. That is {first.value} at week {first.week} and "
            f"{last.value} at week {last.week}."
        )

        if s.unscored_weeks:
            weeks = ", ".join(f"week {w}" for w in s.unscored_weeks)
            lines.append(
                f"{label} was asked about at {weeks} but no rating was given then."
            )

    return lines


def as_chart_data(series: list[Series]) -> list[dict]:
    """The series as plain data, for a frontend to plot.

    Deliberately not a rendering: the brief's text form is `observations`, and
    anything drawing a chart needs the raw points and the scale rather than a
    sentence. `direction` is included because it is subtraction, and no
    interpretation is, because that would not be.
    """
    return [
        {
            "id": s.tracker.id,
            "label": s.tracker.label,
            "question": s.tracker.asked(),
            "scale": {"min": SCALE_MIN, "max": SCALE_MAX, "high_is": "worst"},
            "points": [
                {"week": p.week, "value": p.value, "patient_words": p.patient_words}
                for p in s.points
            ],
            "asked_but_unscored_weeks": s.unscored_weeks,
            "delta": s.delta,
            "direction": s.direction,
        }
        for s in series
    ]
