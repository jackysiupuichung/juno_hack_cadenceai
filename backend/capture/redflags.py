"""Whether the interval's red flags have fired — counted, not judged.

The check-in agent reasons freely about what to ask. This module does not
reason at all. It counts.

The division matters. Deciding whether a symptom cluster has assembled is
arithmetic: the context says two of these seven signs together are worth
surfacing, and the mentions arrive one at a time across calls weeks apart. A
model asked to hold that count across its own prior turns will sometimes be
wrong, and the over-replacement cluster is the single highest-value catch in
this condition — the one the patient never volunteers because the symptoms look
nothing like the complaint they came in with. It has to be exact.

So the agent's job is semantic: turn "my hands won't keep still" into the
canonical phrase "tremor or shaky hands". Whether two such phrases now
constitute a flag is decided here, by counting, against a threshold a clinician
wrote down and cited.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Urgencies that stop a call. "soon" and "routine" are recorded and carried
# into the brief, but do not interrupt: interrupting a check-in to raise
# something that can wait spends the patient's attention badly and makes every
# future call feel like an alarm.
INTERRUPTING_URGENCIES = frozenset({"emergency", "same_day"})


@dataclass(frozen=True)
class FiredFlag:
    """A red flag whose threshold has been met this interval."""

    flag_id: str
    category: str
    urgency: str
    matched: list[str] = field(default_factory=list)
    patient_words: list[str] = field(default_factory=list)
    patient_facing: str = ""
    action: str = ""
    first_seen_week: int = 0
    threshold: int = 1

    @property
    def interrupts(self) -> bool:
        """Whether this should stop the call rather than wait for the brief."""
        return self.urgency in INTERRUPTING_URGENCIES

    @property
    def summary(self) -> str:
        """One line for a log or a CLI trace."""
        signs = ", ".join(self.matched)
        return (
            f"{self.flag_id} [{self.urgency}] "
            f"{len(self.matched)}/{self.threshold} — {signs}"
        )


def evaluate_flags(
    context: dict, mentions: list[dict], *, week: int
) -> list[FiredFlag]:
    """Which flags have fired, given everything reported this interval.

    Args:
        context: The disease context, whose red_flags carry the thresholds.
        mentions: Canonical symptom mentions accumulated across the WHOLE
            interval, not just the current call — each {"watch_for", "flag_id",
            "patient_words", "week"}. Passing only the current call's mentions
            is the one way to use this wrong: a cluster that assembles across
            two calls would never be seen.
        week: The current week, used when a mention carries no week of its own.

    Returns:
        Fired flags, most urgent first. Empty when nothing has met its
        threshold — which is the normal case and not a failure.
    """
    by_flag: dict[str, list[dict]] = {}
    for mention in mentions:
        phrase = mention.get("watch_for")
        if not phrase:
            continue
        by_flag.setdefault(mention.get("flag_id", ""), []).append(mention)

    fired = []
    for flag in context.get("red_flags", []):
        flag_id = flag.get("id", "")
        seen = by_flag.get(flag_id, [])
        if not seen:
            continue

        # A patient repeating the same symptom on three calls has reported one
        # sign, not three. Count distinct signs, in the context's own order so
        # the output is stable.
        distinct = [
            phrase
            for phrase in flag.get("watch_for", [])
            if any(m.get("watch_for") == phrase for m in seen)
        ]

        threshold = flag.get("cluster_threshold", 1)
        if len(distinct) < threshold:
            continue

        fired.append(
            FiredFlag(
                flag_id=flag_id,
                category=flag.get("category", ""),
                urgency=flag.get("urgency", "routine"),
                matched=distinct,
                patient_words=[m.get("patient_words", "") for m in seen],
                # Copied verbatim from the cited file. Nothing here is
                # composed, and nothing patient-facing passes through a model.
                patient_facing=flag.get("patient_facing", ""),
                action=flag.get("action", ""),
                first_seen_week=min(
                    (m.get("week", week) for m in seen), default=week
                ),
                threshold=threshold,
            )
        )

    order = {"emergency": 0, "same_day": 1, "soon": 2, "routine": 3}
    fired.sort(key=lambda f: (order.get(f.urgency, 9), f.first_seen_week))
    return fired
