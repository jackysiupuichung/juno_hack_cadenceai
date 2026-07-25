"""The medication thread: what was prescribed, and where the patient is with it.

A consultation that prescribes something opens a second thread alongside the
symptom one, and it runs on a different clock. Symptoms are asked about every
few weeks; medication is a daily act with its own sequence of failure points —
the prescription is never collected, the first dose is never taken, the label
says something different from what the patient remembers being told, the daily
time drifts. None of those are clinical judgements. They are facts about whether
the plan is actually happening, and each one is invisible to a check-in that
only asks how the symptoms are.

Three things this module is careful about, all of them the same care in
different places:

  - Provenance. A dose has a source: the clinician said it, or the pharmacy
    label printed it, or it is general background. These are never interchange-
    able and never merge. `Source` is carried on the value, not inferred from
    context later, because the moment it is inferred it is wrong.
  - Gaps stay gaps. A field the clinician left vague ("a very low dose") is
    recorded as vague and reported as a gap. Nothing here completes it — not
    from the drug name, not from what is usual, not from the other fields. The
    label fills it or it stays open.
  - Confirmation before it counts. A value read off a photographed label is
    `pending` until the patient has heard it back and said yes. Reminders and
    check-ins use confirmed values only, so a misread label cannot quietly
    become the thing the patient is told to take.

What is deliberately not here: whether the dose is right, whether adherence is
good enough, whether a missed dose matters. This module knows that three doses
were missed. It has no opinion about it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import Enum

# The fields a reminder needs before it can say anything more than "your
# tablet". Ordered as a patient reads them off a label.
LABEL_FIELDS = ("name", "dosage", "frequency", "duration")

# Fields a reminder cannot do without. `duration` is frequently absent from a
# label for an open-ended repeat prescription, so its absence is not a gap worth
# chasing a photo for — but the first three are.
REQUIRED_FOR_REMINDERS = ("name", "dosage", "frequency")

# Phrasings a clinician uses when they are not stating a value. The summariser
# already emits the first of these by contract (visit_summary.schema.json), and
# the others are what unedited speech actually produces. Matching is exact-ish
# rather than clever: a false positive here throws away a real dose.
VAGUE_MARKERS = (
    "unclear",
    "not stated",
    "not specified",
    "unknown",
    "as directed",
    "as before",
    "same as",
    "tbc",
    "to be confirmed",
)

# Qualifiers that describe a dose without being one. "a very low dose" is what
# the demo consultation actually contains, and it is the exact case the label
# exists to resolve: it means something to the clinician and nothing to a
# reminder.
UNQUANTIFIED_DOSE_MARKERS = (
    "low dose",
    "high dose",
    "small dose",
    "standard dose",
    "usual dose",
    "starting dose",
    "normal dose",
)

# How long to keep asking about an uncollected prescription before it stops
# being a reminder and starts being nagging. The brief asks for "sensibly, with-
# out nagging"; this is that, made arithmetic.
COLLECTION_CHASE_DAYS = 14

# Days after the first dose to run the adherence check. Early enough that a
# habit is still forming and a problem is still fixable, late enough that there
# is something to report.
ADHERENCE_CHECK_DAYS = 5


class Source(str, Enum):
    """Where a value came from. Never inferred, never merged across sources.

    The brief's "separate sources" principle, made a type. CLINICIAN is
    authoritative and attributed to them; LABEL fills gaps and is marked as
    label-sourced; GENERAL is background that must never be presented as
    something the clinician said.
    """

    CLINICIAN = "clinician"
    LABEL = "label"
    GENERAL = "general"


class Confirmation(str, Enum):
    """Whether a value may be acted on yet.

    A label value is PENDING from the moment it is extracted until the patient
    has heard it read back and agreed. Only CONFIRMED values reach a reminder.
    """

    CONFIRMED = "confirmed"
    PENDING = "pending"
    REJECTED = "rejected"


class Collection(str, Enum):
    """Where the prescription itself has got to."""

    UNKNOWN = "unknown"
    NOT_COLLECTED = "not_collected"
    COLLECTED = "collected"
    NOT_APPLICABLE = "not_applicable"


class Adherence(str, Enum):
    """What the patient said about taking it. Recorded, never graded."""

    UNKNOWN = "unknown"
    EVERY_DAY = "every_day"
    MISSED_ONCE = "missed_once"
    MISSED_MORE = "missed_more"
    STOPPED = "stopped"


@dataclass(frozen=True)
class Value:
    """One field of a medication, with where it came from and whether it counts.

    Frozen because a value's provenance must not be edited in place — a LABEL
    value that becomes a CLINICIAN value by assignment is exactly the confusion
    the type exists to prevent. Corrections replace the whole value.
    """

    text: str
    source: Source
    confirmation: Confirmation = Confirmation.CONFIRMED

    @property
    def is_stated(self) -> bool:
        """True when this is an actual value rather than a gap or a hedge."""
        return bool(self.text.strip()) and not _is_vague(self.text)

    @property
    def is_usable(self) -> bool:
        """True when a reminder may use it: stated, and agreed to."""
        return self.is_stated and self.confirmation is Confirmation.CONFIRMED

    def attributed(self) -> str:
        """The value with its source named, for anything patient-facing.

        Every place a value is spoken aloud goes through here, so the patient
        always hears which of the three sources they are being told about.
        """
        if not self.is_stated:
            return "not stated"
        if self.source is Source.CLINICIAN:
            return f"{self.text} (as your clinician said)"
        if self.source is Source.LABEL:
            return f"{self.text} (from the pharmacy label)"
        return f"{self.text} (general information, not from your clinician)"


def _is_vague(text: str) -> bool:
    """Whether a stated field is really a gap wearing a value's clothes.

    Two kinds: an explicit hedge from the summariser ("unclear — please confirm")
    and an unquantified qualifier from ordinary speech ("a very low dose"). Both
    read as filled and are not, which is worse than an empty string because
    nothing downstream thinks to ask.
    """
    lowered = text.strip().lower()
    if not lowered:
        return True
    if any(marker in lowered for marker in VAGUE_MARKERS):
        return True
    # A qualifier is only a gap when it carries no number with it. "low dose,
    # 25mcg" is a stated dose that happens to be described as low.
    if any(marker in lowered for marker in UNQUANTIFIED_DOSE_MARKERS):
        return not any(ch.isdigit() for ch in lowered)
    return False


@dataclass
class Medication:
    """One prescribed medicine and the state of the thread that follows it.

    Assembled from the visit summary, then updated by check-ins and by a
    photographed label. Every clinical field is a `Value` so its provenance
    travels with it; everything else on here is thread state, which has no
    provenance question because it comes from the patient directly.
    """

    name: Value
    dosage: Value
    frequency: Value
    duration: Value
    instructions: Value

    collection: Collection = Collection.UNKNOWN
    first_dose_taken: bool | None = None
    reminder_time: str = ""          # "07:30", as the patient chose it
    adherence: Adherence = Adherence.UNKNOWN
    label_seen: bool = False
    last_chased_day: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name.text or "your medication"

    @property
    def gaps(self) -> list[str]:
        """Which reminder-critical fields are still missing or vague.

        This is what makes a medication card "incomplete" and prompts the label
        photo. Deliberately computed rather than stored: a gap closes the moment
        a confirmed value arrives, and a stored flag would go stale.
        """
        return [
            field_name
            for field_name in REQUIRED_FOR_REMINDERS
            if not getattr(self, field_name).is_usable
        ]

    @property
    def is_complete(self) -> bool:
        return not self.gaps

    @property
    def pending_confirmation(self) -> list[str]:
        """Fields read off a label that the patient has not yet agreed to."""
        return [
            field_name
            for field_name in LABEL_FIELDS
            if getattr(self, field_name).confirmation is Confirmation.PENDING
        ]

    @property
    def needs_label_photo(self) -> bool:
        """Whether to ask for the label.

        Only worth asking once they have it in their hands — a photo of a
        prescription that is still at the pharmacy does not exist. An
        already-seen label that did not close the gaps is not re-requested;
        that is a question for the patient, not another photo.
        """
        return (
            bool(self.gaps)
            and self.collection is Collection.COLLECTED
            and not self.label_seen
        )

    @property
    def reminders_ready(self) -> bool:
        """Whether the daily reminder can say anything specific yet.

        Needs the fields and the time. Without the time there is nothing to
        schedule; without the fields the reminder would have to name a dose it
        does not actually know.
        """
        return self.is_complete and bool(self.reminder_time)

    def as_line(self) -> str:
        """The medication as one attributed line, for reading back.

        Used for the confirmation step: the patient hears this and says whether
        it is right, before any of it reaches a reminder.
        """
        parts = [self.display_name]
        for field_name in ("dosage", "frequency"):
            value = getattr(self, field_name)
            if value.is_stated:
                parts.append(value.text)
        line = " — ".join(parts)

        sources = {
            getattr(self, f).source
            for f in LABEL_FIELDS
            if getattr(self, f).is_stated
        }
        if sources == {Source.LABEL}:
            return f"{line} (from the pharmacy label)"
        if Source.LABEL in sources:
            return f"{line} (partly from the pharmacy label)"
        return line


def _value(raw: object, source: Source) -> Value:
    """Coerce a summary field into a Value without inventing anything."""
    return Value(text=str(raw or "").strip(), source=source)


def from_summary(summary: dict) -> list[Medication]:
    """The medication thread as the consultation left it.

    Every field is CLINICIAN-sourced and CONFIRMED — the clinician said it, so
    it needs no confirming — but a vague one is still a gap, which is why
    `is_stated` and `confirmation` are separate questions. "Very low dose", said
    by a doctor, is authoritative and unusable at the same time.

    Returns an empty list when nothing was prescribed. That is the signal the
    whole medication thread is switched off for this interval, not a degenerate
    case to work around: most consultations do not prescribe.
    """
    medications = []
    for entry in summary.get("medications") or []:
        if isinstance(entry, dict):
            medications.append(
                Medication(
                    name=_value(entry.get("name"), Source.CLINICIAN),
                    dosage=_value(entry.get("dosage"), Source.CLINICIAN),
                    frequency=_value(entry.get("frequency"), Source.CLINICIAN),
                    duration=_value(entry.get("duration"), Source.CLINICIAN),
                    instructions=_value(entry.get("instructions"), Source.CLINICIAN),
                )
            )
        elif entry:
            # A bare string is all some summaries carry. It names the drug and
            # nothing else, which is three gaps, correctly.
            medications.append(
                Medication(
                    name=_value(entry, Source.CLINICIAN),
                    dosage=Value("", Source.CLINICIAN),
                    frequency=Value("", Source.CLINICIAN),
                    duration=Value("", Source.CLINICIAN),
                    instructions=Value("", Source.CLINICIAN),
                )
            )
    return medications


def apply_label(medication: Medication, extracted: dict) -> Medication:
    """Fill this medication's gaps from what a pharmacy label printed.

    Gap-fill only, and this is the load-bearing rule: a label never overwrites
    something the clinician stated. If the two disagree, the clinician's value
    stands and the discrepancy is recorded as a note for the patient to raise —
    it is not this system's place to decide which is right, and silently
    preferring either one would hide a real problem.

    Extracted values arrive PENDING. They become usable only after
    `confirm_label`, which happens once the patient has heard them read back.
    """
    updates: dict[str, Value] = {}
    notes = list(medication.notes)

    for field_name in LABEL_FIELDS:
        printed = str(extracted.get(field_name, "") or "").strip()
        if not printed:
            continue

        current: Value = getattr(medication, field_name)
        if current.is_stated and current.source is Source.CLINICIAN:
            if printed.lower() != current.text.strip().lower():
                notes.append(
                    f"The label says {field_name} is \"{printed}\"; your "
                    f"clinician said \"{current.text}\". Worth checking with "
                    f"them which to follow."
                )
            continue

        updates[field_name] = Value(
            text=printed, source=Source.LABEL, confirmation=Confirmation.PENDING
        )

    return replace(medication, label_seen=True, notes=notes, **updates)


def confirm_label(medication: Medication, *, accepted: bool) -> Medication:
    """Settle every pending label value, once the patient has heard them back.

    Rejection clears the values rather than keeping them as rejected text: a
    value the patient says is wrong is worse than no value, because it looks
    filled. Clearing it reopens the gap, which is the honest state.
    """
    updates: dict[str, Value] = {}
    for field_name in LABEL_FIELDS:
        value: Value = getattr(medication, field_name)
        if value.confirmation is not Confirmation.PENDING:
            continue
        updates[field_name] = (
            replace(value, confirmation=Confirmation.CONFIRMED)
            if accepted
            else Value("", Source.LABEL, Confirmation.REJECTED)
        )
    return replace(medication, **updates)


@dataclass(frozen=True)
class MedicationTask:
    """One thing the medication thread needs from the patient right now.

    Emitted by `due_tasks` and rendered into the agent's prompt as an aim, in
    exactly the way plan.py renders agenda items: what to establish, never a
    sentence to read out.
    """

    kind: str          # collect | first_dose | label_photo | confirm_label
                       # | reminder_time | adherence | unclear_instructions
    medication: str    # display name
    intent: str
    priority: int = 1


def due_tasks(medications: list[Medication], *, day: int) -> list[MedicationTask]:
    """What the medication thread needs establishing, on this day of the interval.

    Ordered most important first, and deliberately short: a call that opens with
    six medication questions is the nagging the brief warns against. The
    sequencing is the point — nothing asks about doses before the prescription
    is collected, nothing asks for a label photo before there is a label, and
    nothing chases a collection past the point where chasing becomes pressure.

    Args:
        medications: The thread's current state, from `from_summary` plus
            whatever check-ins have since recorded.
        day: Days since the consultation. Days rather than weeks because this
            thread's first contact is the day after, and its adherence check is
            five days in — a week-grained clock cannot see either.
    """
    tasks: list[MedicationTask] = []

    for med in medications:
        name = med.display_name

        if med.collection in (Collection.UNKNOWN, Collection.NOT_COLLECTED):
            # Chasing stops being a reminder and becomes pressure. After the
            # window it is left for the person, not asked again.
            if day <= COLLECTION_CHASE_DAYS:
                tasks.append(
                    MedicationTask(
                        kind="collect",
                        medication=name,
                        intent=f"whether they have collected {name} from the pharmacy yet",
                        priority=1,
                    )
                )
            continue

        if med.first_dose_taken is None:
            tasks.append(
                MedicationTask(
                    kind="first_dose",
                    medication=name,
                    intent=f"whether they have taken the first dose of {name}",
                    priority=1,
                )
            )

        if med.pending_confirmation:
            tasks.append(
                MedicationTask(
                    kind="confirm_label",
                    medication=name,
                    intent=(
                        f"read back what the label says — \"{med.as_line()}\" — "
                        "and get a yes or no before it is saved"
                    ),
                    priority=1,
                )
            )
        elif med.needs_label_photo:
            tasks.append(
                MedicationTask(
                    kind="label_photo",
                    medication=name,
                    intent=(
                        f"ask them to photograph the {name} pharmacy label — the "
                        f"consultation did not state its {', '.join(med.gaps)}"
                    ),
                    priority=1,
                )
            )

        if not med.reminder_time:
            tasks.append(
                MedicationTask(
                    kind="reminder_time",
                    medication=name,
                    intent=f"what time each day they will take {name}, to set the daily reminder",
                    priority=2,
                )
            )

        if (
            med.first_dose_taken
            and med.adherence is Adherence.UNKNOWN
            and day >= ADHERENCE_CHECK_DAYS
        ):
            tasks.append(
                MedicationTask(
                    kind="adherence",
                    medication=name,
                    intent=(
                        f"how taking {name} has actually gone — every day, missed "
                        "once, missed more than once — and what makes it hard"
                    ),
                    priority=2,
                )
            )

    return sorted(tasks, key=lambda t: t.priority)


def daily_reminder(medication: Medication) -> str:
    """The daily nudge, or "" when there is not enough to say one.

    Short and warm by construction, and it reproduces only the clinician's own
    timing instruction — never a rule they did not give. General background
    about the drug belongs in a labelled note, not here; that is why nothing in
    this function reads anything but stated fields.

    Returns "" rather than a generic nudge when the thread is not ready: a
    reminder that cannot name the dose is a reminder that will be ignored, and
    the honest response to an incomplete card is to close the gap first.
    """
    if not medication.reminders_ready:
        return ""

    line = f"Time for your {medication.name.text} — {medication.dosage.text}."

    # Only the clinician's own timing words, and only the short ones. A whole
    # paragraph of instructions read out daily stops being a nudge.
    instruction = medication.instructions
    if instruction.is_stated and instruction.source is Source.CLINICIAN:
        first_clause = instruction.text.split(";")[0].strip().rstrip(".")
        if first_clause and len(first_clause) <= 80:
            line += f" Your clinician said: {first_clause}."

    return line


def as_agent_brief(medications: list[Medication], *, day: int) -> str:
    """The medication thread rendered for a check-in agent's system prompt.

    Returns "" when nothing was prescribed, so an interval with no medication
    gets no medication section at all rather than an empty heading — an agent
    shown "Medications: (none)" will find something to ask about it.
    """
    if not medications:
        return ""

    lines = ["What they were prescribed, and where the thread has got to:"]

    for med in medications:
        lines.append(f"  {med.display_name}")
        for field_name in ("dosage", "frequency", "duration"):
            value: Value = getattr(med, field_name)
            lines.append(f"      {field_name}: {value.attributed()}")

        state = [f"collection: {med.collection.value}"]
        if med.first_dose_taken is not None:
            state.append(f"first dose: {'taken' if med.first_dose_taken else 'not taken'}")
        if med.reminder_time:
            state.append(f"daily reminder set for {med.reminder_time}")
        if med.adherence is not Adherence.UNKNOWN:
            state.append(f"adherence as reported: {med.adherence.value}")
        lines.append(f"      {'; '.join(state)}")

        if med.gaps:
            lines.append(
                f"      not established: {', '.join(med.gaps)} — "
                "ask the patient or fill from the label; never infer it"
            )
        for note in med.notes:
            lines.append(f"      note: {note}")

    tasks = due_tasks(medications, day=day)
    if tasks:
        lines.append("\nWhat the medication thread needs from this call (aims, not questions):")
        for task in tasks:
            lines.append(f"  [med_{task.kind}] p{task.priority} {task.intent}")

    return "\n".join(lines)


def observations(medications: list[Medication]) -> list[str]:
    """Factual statements about the medication thread, for the brief.

    Same contract as interval.observations: dated facts, no conclusions. "Missed
    more than one dose" is a fact the doctor can use; "adherence is poor" is a
    judgement this system does not make.
    """
    lines = []
    for med in medications:
        name = med.display_name

        if med.collection is Collection.NOT_COLLECTED:
            lines.append(f"Not collected from the pharmacy: {name}.")
        elif med.collection is Collection.UNKNOWN:
            lines.append(f"Never established whether {name} was collected.")

        if med.first_dose_taken is False:
            lines.append(f"Reported not having taken a first dose of {name}.")

        if med.adherence is Adherence.MISSED_ONCE:
            lines.append(f"Reported missing one dose of {name}.")
        elif med.adherence is Adherence.MISSED_MORE:
            lines.append(f"Reported missing more than one dose of {name}.")
        elif med.adherence is Adherence.STOPPED:
            lines.append(f"Reported having stopped taking {name}.")

        if med.gaps:
            sourced = "the consultation did not state"
            lines.append(f"{sourced} {name}'s {', '.join(med.gaps)}.".capitalize())

        for note in med.notes:
            lines.append(note)

    return lines


def first_contact_day(visit_date: date) -> date:
    """When the caretaker makes first contact: the day after the consultation."""
    return visit_date + timedelta(days=1)


def days_since(visit_date: date, today: date) -> int:
    """Days elapsed, floored at zero for the same reason weeks are."""
    return max(0, (today - visit_date).days)
