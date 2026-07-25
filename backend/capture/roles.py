"""Infer which diarized speaker is the clinician and which is the patient.

Scribe returns anonymous labels (`speaker_0`, `speaker_1`). Everything
downstream — the summary fields, the commitment extraction — depends on knowing
who said what, so we resolve those labels to DOCTOR and PATIENT here rather
than leaving it to the LLM to guess mid-summary.

Deliberately heuristic and deterministic: this runs on every capture, needs to
be testable, and a wrong-but-confident LLM answer here would corrupt every
field downstream. When the signal is weak we say so via `confidence` rather
than guessing silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DOCTOR = "DOCTOR"
PATIENT = "PATIENT"
UNKNOWN = "UNKNOWN"

# Phrases a clinician says and a patient essentially never does: directing the
# consultation, ordering, prescribing, examining.
DOCTOR_CUES = (
    r"\bwhat brought you in\b",
    r"\bhow can i help\b",
    r"\bwhat brings you (in|here)\b",
    r"\bi'?ll (send|order|refer|prescribe|write)\b",
    r"\bi'?m (going to |gonna )?(order|refer|prescrib)\w*\b",
    r"\bi'?d like to (start|order|check|refer)\b",
    r"\bwe('| a)?ll (start|try|book|order|check)\b",
    r"\blet'?s (try|start|book|check|see)\b",
    r"\bi'?m just looking at your\b",
    r"\byour (blood )?(results?|levels?|tests?)\b",
    r"\bthe best treatment\b",
    r"\bprescription\b",
    r"\btake (these|this) (medication|tablet|pill)\w*\b",
    r"\bseek (some )?help\b",
    r"\bany (other )?(questions|concerns)\b",
    r"\bdo you (think you )?can do that\b",
    r"\bhave you ever (had|heard of|tried)\b",
    r"\bcome back (if|in|sooner)\b",
    r"\bfollow(-| )up\b",
    r"\bmilligram\w*\b",
    r"\bdosage\b",
    r"\bon an empty stomach\b",
)

# Phrases that mark the person reporting symptoms and receiving instructions.
PATIENT_CUES = (
    r"\bi (came|come) in with\b",
    r"\bi'?ve been (feeling|having|getting)\b",
    r"\bi (feel|felt) \w+",
    r"\bi (have|had|get|got) (some |a )?(pain|ache|fatigue|nausea|dizziness)\b",
    r"\bmy (skin|heart|head|chest|stomach|leg|arm|sleep|symptoms?)\b",
    r"\bi noticed\b",
    r"\bi don'?t know (if|much|what)\b",
    r"\bi haven'?t\b",
    r"\bit (hurts|aches)\b",
    r"\bi'?ll try\b",
    r"\bthank you,? doctor\b",
    r"\bdoctor,?\s+i\b",
)

# Weighted lower than cue phrases: a real signal, but noisier.
_QUESTION_RE = re.compile(r"\?")
_FIRST_PERSON_SYMPTOM_RE = re.compile(
    r"\bmy\b|\bi\s+(feel|felt|have|had|noticed|got|get)\b", re.IGNORECASE
)


@dataclass
class RoleAssignment:
    """Which speaker label maps to which role, and how sure we are."""

    roles: dict[str, str]
    confidence: str  # "high" | "low" | "none"
    scores: dict[str, dict[str, float]]

    def role_for(self, speaker: str) -> str:
        return self.roles.get(speaker, UNKNOWN)


def _count_cues(text: str, patterns: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for pattern in patterns if re.search(pattern, lowered))


def _score_speaker(turns: list[str]) -> dict[str, float]:
    """Score one speaker's turns for doctor-ness and patient-ness."""
    joined = " ".join(turns)

    doctor_score = float(_count_cues(joined, DOCTOR_CUES))
    patient_score = float(_count_cues(joined, PATIENT_CUES))

    # The clinician drives the consultation, so they ask most of the questions.
    questions = sum(1 for t in turns if _QUESTION_RE.search(t))
    question_rate = questions / len(turns) if turns else 0.0
    doctor_score += question_rate * 2.0

    # The patient talks about their own body.
    symptom_turns = sum(1 for t in turns if _FIRST_PERSON_SYMPTOM_RE.search(t))
    symptom_rate = symptom_turns / len(turns) if turns else 0.0
    patient_score += symptom_rate * 2.0

    return {
        "doctor": doctor_score,
        "patient": patient_score,
        "net": doctor_score - patient_score,
    }


def infer_roles(utterances) -> RoleAssignment:
    """Map diarized speaker labels onto DOCTOR / PATIENT.

    Scores each speaker independently, then assigns roles by comparing their
    net doctor-ness. Handles the common two-speaker case; with other speaker
    counts, only the clearest doctor and patient are labelled.
    """
    by_speaker: dict[str, list[str]] = {}
    for utterance in utterances:
        by_speaker.setdefault(utterance.speaker, []).append(utterance.text)

    scores = {s: _score_speaker(turns) for s, turns in by_speaker.items()}

    if not scores:
        return RoleAssignment(roles={}, confidence="none", scores={})

    if len(scores) == 1:
        # A single speaker can't be resolved by comparison. Use the raw signal:
        # a lone voice describing their own symptoms is the patient.
        speaker, score = next(iter(scores.items()))
        if score["net"] > 0:
            role, confidence = DOCTOR, "low"
        elif score["net"] < 0:
            role, confidence = PATIENT, "low"
        else:
            role, confidence = UNKNOWN, "none"
        return RoleAssignment({speaker: role}, confidence, scores)

    # Rank by net doctor-ness: highest is the doctor, lowest the patient.
    ranked = sorted(scores.items(), key=lambda kv: kv[1]["net"], reverse=True)
    doctor_speaker, doctor_score = ranked[0]
    patient_speaker, patient_score = ranked[-1]

    roles = {speaker: UNKNOWN for speaker in scores}
    margin = doctor_score["net"] - patient_score["net"]

    if margin <= 0:
        # No separation at all — refuse rather than coin-flip.
        return RoleAssignment(roles, "none", scores)

    roles[doctor_speaker] = DOCTOR
    roles[patient_speaker] = PATIENT
    confidence = "high" if margin >= 2.0 else "low"

    return RoleAssignment(roles, confidence, scores)
