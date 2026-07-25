"""The last check on anything Cadence says out loud.

Cadence documents and supports; it does not diagnose or prescribe. That line is
the regulatory footing for the whole product — patient-side self-management
sits in a different universe from clinical decision support — and it is easiest
to cross by accident, in a sentence that sounds helpful.

A scripted agent barely needs this. Ours is not scripted: it reads the whole
disease context, including typical treatment, dose language and guideline
rationale, and composes its own questions. That is more rope. So every
utterance passes through here before it reaches the patient.

This is a backstop, not the main defence. Most enforcement is structural — the
turn schema gives the model nowhere to put a dose recommendation, and every
patient-facing warning is copied verbatim from the cited context rather than
composed. This catches the residue in the one free-text field that remains.

It fails closed to a neutral acknowledgement rather than raising. A check-in
that dies mid-sentence is worse for the patient than one that says less, and a
dropped question costs a line in the brief's gaps — which is honest output, not
a failure.
"""

from __future__ import annotations

import re

FALLBACK = "Thanks, I've noted that down."

# Keyed to the prohibited_outputs in the disease context. Deliberately a short
# table of the phrasings that actually occur, not a taxonomy of everything that
# could: an over-eager filter that scrubs ordinary conversation is its own
# failure mode, and the tests hold both ends of that.
_DOSE_VERBS = (
    r"(?:increas\w*|reduc\w*|lower\w*|rais\w*|stop\w*|halv\w*|split\w*|"
    r"doubl\w*|adjust\w*|chang\w*|skip\w*|cut\w*)"
)
_DOSE_NOUNS = r"(?:dose|dosage|tablet|tablets|pill|pills|mg|microgram\w*|levothyroxine|medication|medicine)"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "suggests a change to the dose or medication",
        re.compile(
            rf"\b(?:you\s+(?:should|could|might|may|need\s+to|ought\s+to)|"
            rf"try|consider|i'd\s+suggest|i\s+suggest|i'd\s+recommend|"
            rf"it'?s\s+worth)\b[^.?!]{{0,60}}\b{_DOSE_VERBS}\b[^.?!]{{0,40}}\b{_DOSE_NOUNS}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "suggests a change to the dose or medication",
        re.compile(
            rf"\b{_DOSE_VERBS}\s+(?:your|the|a|one|half)?\s*{_DOSE_NOUNS}",
            re.IGNORECASE,
        ),
    ),
    (
        "attributes a cause to a symptom",
        re.compile(
            r"\b(?:that'?s|this\s+is|that\s+is|it'?s)\s+(?:probably|likely|"
            r"almost\s+certainly|because|due\s+to|caused\s+by|a\s+sign\s+of|"
            r"a\s+symptom\s+of)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "attributes a cause to a symptom",
        re.compile(
            r"\b(?:caused\s+by|because\s+of|due\s+to|a\s+result\s+of)\s+"
            r"(?:the|your)\s+(?:tablet\w*|medication|dose|levothyroxine|treatment)",
            re.IGNORECASE,
        ),
    ),
    (
        "interprets a test result",
        re.compile(
            r"\byour\s+(?:tsh|t4|ft4|thyroid\s+level\w*|level\w*|result\w*|"
            r"blood\s*\w*|test\w*)\b[^.?!]{0,20}?\b"
            r"(?:are|is|were|was|look\w*|seem\w*|came\s+back|coming\s+back)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "says the treatment is or is not working",
        re.compile(
            r"\b(?:(?:is|isn'?t|is\s+not|not)\s+working|working\s+well|"
            r"treatment\s+(?:is\s+)?fail\w*|not\s+doing\s+(?:its|the)\s+job)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommends a test or referral the doctor did not raise",
        re.compile(
            r"\byou\s+(?:should|need\s+to|ought\s+to|might\s+want\s+to)\s+"
            r"(?:get|book|ask\s+for|request|arrange|have)\s+"
            r"(?:a|an|another|some)?\s*"
            r"(?:blood\s+test|test|scan|referral|appointment\s+with\s+a\s+specialist)",
            re.IGNORECASE,
        ),
    ),
    (
        "frames the interval as going wrong",
        re.compile(
            r"\b(?:you\s+should\s+be\s+(?:feeling\s+)?better\s+by\s+now|"
            r"that'?s\s+(?:too\s+slow|not\s+right|concerning|worrying)|"
            r"something\s+(?:'?s|is)\s+(?:wrong|not\s+right)|"
            r"that\s+(?:doesn'?t|does\s+not)\s+sound\s+right)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "offers a clinical opinion",
        re.compile(
            r"\b(?:in\s+my\s+(?:opinion|view)|i\s+think\s+(?:you|that)\s+"
            r"(?:have|might\s+have|are)\b|medically\s+speaking)",
            re.IGNORECASE,
        ),
    ),
]


def check_utterance(text: str, context: dict | None = None) -> list[str]:
    """Which prohibitions, if any, this sentence breaks.

    Args:
        text: What the agent proposes to say.
        context: The disease context. Accepted so callers can pass it
            uniformly; the patterns are condition-independent, and the
            context's own prohibited_outputs are what they were written from.

    Returns:
        Violation reasons, deduped and ordered. Empty means the line is clean.
    """
    if not text or not text.strip():
        return []

    reasons: list[str] = []
    for reason, pattern in PATTERNS:
        if pattern.search(text) and reason not in reasons:
            reasons.append(reason)
    return reasons


def scrub(text: str, context: dict | None = None, *, fallback: str = FALLBACK) -> str:
    """Return the text if it is safe to say, or a neutral line if it is not.

    Whole-utterance replacement rather than surgical excision: a sentence that
    crosses the line usually does so as a whole thought, and patching out a
    clause tends to leave something that still implies the claim. Losing the
    turn is cheap; half-retracting a clinical statement is not.
    """
    return fallback if check_utterance(text, context) else text
