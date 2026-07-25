"""What the caretaker knows about the person before it says a word.

Everything the check-in agent currently holds is clinical: the interval facts,
the disease context, the agenda, the medication thread. That is enough to know
what to ask and nothing at all about how to ask it. The result is a call that is
correct and stilted — it uses a name the patient does not go by, rings at 9am
when they work nights, and asks whether they have been taking the tablet without
knowing they cannot swallow tablets.

None of that is clinical information, which is why none of it lives in the
disease context. The disease context is a curated reference shared by every
patient with that condition. This is the opposite: it belongs to one person, it
follows them across every condition they have, and no visit summary contains it
because a clinician never dictates it.

The boundary this module holds, and it is the same one as everywhere else: these
are facts about circumstances, never clinical judgements. "Cannot swallow
tablets" is a circumstance and belongs here. "Should be switched to a liquid
formulation" is a treatment change, and does not.

One consequence worth naming. `access_needs` and `medication_barriers` are
rendered to the agent as things to accommodate, not as things to solve. An agent
told "cannot swallow tablets" and left to its own devices will suggest crushing
them, which is a medication-administration change and squarely across the CDS
line. So the rendering says what to do with the fact — work around it, and
record it for the brief — rather than handing it over bare.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# How many agenda items a call should carry, by how much the patient can take.
# The wedge population tires easily; fatigue is a core symptom, not a footnote.
# A call that is fine for one person is exhausting for another, and the honest
# response is a shorter call, not the same call delivered faster.
CALL_LENGTH_ITEMS = {
    "brief": 2,
    "standard": 4,
    "unhurried": 6,
}

DEFAULT_CALL_LENGTH = "standard"


@dataclass
class CaretakerContext:
    """The standing facts about a patient that shape how the caretaker speaks.

    Every field is optional and defaults empty. A patient Cadence has only just
    met has no context at all, and the correct behaviour then is an ordinary
    call — not a call that stalls asking who it is talking to.
    """

    preferred_name: str = ""
    contact_window: str = ""
    call_length_preference: str = DEFAULT_CALL_LENGTH

    living_situation: str = ""
    access_needs: list[str] = field(default_factory=list)
    medication_barriers: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)

    supporter_name: str = ""
    supporter_relationship: str = ""
    supporter_may_be_contacted: bool = False

    notes: str = ""

    @property
    def is_empty(self) -> bool:
        """True when there is nothing here worth putting in a prompt.

        Checked rather than assumed, because the difference between an empty
        context and a missing one is nothing to the agent: both mean it knows
        nothing about the person, and both should produce no section at all
        rather than a heading with nothing under it.
        """
        return not any(
            (
                self.preferred_name.strip(),
                self.contact_window.strip(),
                self.living_situation.strip(),
                self.access_needs,
                self.medication_barriers,
                self.priorities,
                self.supporter_name.strip(),
                self.notes.strip(),
            )
        )

    @property
    def max_call_items(self) -> int:
        """How many things this call should try to cover."""
        return CALL_LENGTH_ITEMS.get(self.call_length_preference, CALL_LENGTH_ITEMS[DEFAULT_CALL_LENGTH])

    def address_as(self, fallback: str = "") -> str:
        """What to call them. Their preferred name, or the record's, or nothing.

        Returning "" is deliberate and is handled by the caller: an agent with
        no name to use writes around it, which is ordinary conversation. A
        placeholder would be read aloud.
        """
        return self.preferred_name.strip() or fallback.strip()


def from_row(row: dict | None) -> CaretakerContext:
    """A caretaker_context row as a value. A missing row is an empty context."""
    if not row:
        return CaretakerContext()
    return CaretakerContext(
        preferred_name=row.get("preferred_name") or "",
        contact_window=row.get("contact_window") or "",
        call_length_preference=row.get("call_length_preference") or DEFAULT_CALL_LENGTH,
        living_situation=row.get("living_situation") or "",
        access_needs=list(row.get("access_needs") or []),
        medication_barriers=list(row.get("medication_barriers") or []),
        priorities=list(row.get("priorities") or []),
        supporter_name=row.get("supporter_name") or "",
        supporter_relationship=row.get("supporter_relationship") or "",
        supporter_may_be_contacted=bool(row.get("supporter_may_be_contacted")),
        notes=row.get("notes") or "",
    )


def to_row(context: CaretakerContext, patient_id: str) -> dict:
    """The context as a database row, minus its id."""
    return {
        "patient_id": patient_id,
        "preferred_name": context.preferred_name,
        "contact_window": context.contact_window,
        "call_length_preference": context.call_length_preference,
        "living_situation": context.living_situation,
        "access_needs": context.access_needs,
        "medication_barriers": context.medication_barriers,
        "priorities": context.priorities,
        "supporter_name": context.supporter_name,
        "supporter_relationship": context.supporter_relationship,
        # Consent is never carried without the person it refers to. The database
        # constraint says the same thing; this stops a value that would fail it
        # from ever being sent, so the failure is a corrected write rather than
        # a 400 halfway through a call.
        "supporter_may_be_contacted": (
            context.supporter_may_be_contacted and bool(context.supporter_name.strip())
        ),
        "notes": context.notes,
    }


def as_agent_brief(context: CaretakerContext) -> str:
    """The context rendered for a check-in agent's system prompt.

    Returns "" for an empty context, so a patient Cadence knows nothing about
    gets no section rather than a heading full of blanks — the same rule the
    medication thread follows, and for the same reason: an agent shown an empty
    section will find something to do with it.

    Written as facts followed by what to do with them. The instruction is not
    decoration: several of these are things an agent would otherwise try to
    solve, and solving them means suggesting a change to how medication is
    taken, which is the line Cadence does not cross.
    """
    if context.is_empty:
        return ""

    lines = ["Who you are speaking to:"]

    if context.preferred_name.strip():
        lines.append(f"  They go by {context.preferred_name.strip()}. Use it.")

    if context.contact_window.strip():
        lines.append(
            f"  When they can talk: {context.contact_window.strip()}. If they say "
            "this is a bad moment, offer to ring back rather than pressing on."
        )

    lines.append(
        f"  Keep this call {context.call_length_preference}: aim to cover at most "
        f"{context.max_call_items} things, and stop early if they are tiring. "
        "Leaving a question unasked and saying so is better than a call they "
        "cannot finish."
    )

    if context.living_situation.strip():
        lines.append(f"  Their situation: {context.living_situation.strip()}")

    if context.access_needs:
        lines.append(
            "  Accommodate, without remarking on it: "
            + "; ".join(context.access_needs)
        )

    if context.medication_barriers:
        lines.append(
            "  What makes taking medication hard for them: "
            + "; ".join(context.medication_barriers)
            + ". Take this into account when you ask how it is going, and record "
            "anything new they say about it. Do not suggest a way around it — "
            "how medication is taken is their clinician's to change, not yours."
        )

    if context.priorities:
        lines.append(
            "  What they have said matters to them: "
            + "; ".join(context.priorities)
            + ". Worth remembering when they tell you how things are going."
        )

    if context.supporter_name.strip():
        relationship = context.supporter_relationship.strip() or "someone who helps them"
        if context.supporter_may_be_contacted:
            consent = (
                "They have agreed this person can be spoken to about their care."
            )
        else:
            consent = (
                "They have NOT agreed to this person being told anything. Do not "
                "discuss their care with anyone else who answers the phone."
            )
        lines.append(f"  {context.supporter_name.strip()} ({relationship}). {consent}")

    if context.notes.strip():
        lines.append(f"  Also worth knowing: {context.notes.strip()}")

    return "\n".join(lines)
