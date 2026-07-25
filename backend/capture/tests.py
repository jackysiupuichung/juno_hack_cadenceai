"""Tests for conversation tracking and speaker role inference."""

import json
from pathlib import Path

from django.test import TestCase

from .roles import DOCTOR, PATIENT, UNKNOWN, infer_roles
from .transcribe import Transcript, Utterance, _group_into_utterances

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo_consultation.json"


def _turns(*pairs) -> list[Utterance]:
    """Build utterances from (speaker, text) pairs with sequential timings."""
    return [
        Utterance(speaker=s, text=t, start=float(i), end=float(i) + 0.9)
        for i, (s, t) in enumerate(pairs)
    ]


class GroupIntoUtterancesTests(TestCase):
    def _word(self, text, speaker=None, type_="word", start=None, end=None):
        return {
            "text": text,
            "speaker_id": speaker,
            "type": type_,
            "start": start,
            "end": end,
        }

    def test_consecutive_words_from_one_speaker_become_one_utterance(self):
        words = [
            self._word("So", "speaker_0", start=0.0, end=0.2),
            self._word(" ", type_="spacing"),
            self._word("how", "speaker_0", start=0.2, end=0.4),
            self._word(" ", type_="spacing"),
            self._word("are", "speaker_0", start=0.4, end=0.6),
        ]
        utterances = _group_into_utterances(words)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0].text, "So how are")

    def test_speaker_change_starts_a_new_utterance(self):
        words = [
            self._word("Hello", "speaker_0", start=0.0, end=0.5),
            self._word("Hi", "speaker_1", start=1.0, end=1.5),
            self._word("Okay", "speaker_0", start=2.0, end=2.5),
        ]
        utterances = _group_into_utterances(words)
        self.assertEqual(
            [u.speaker for u in utterances],
            ["speaker_0", "speaker_1", "speaker_0"],
        )

    def test_utterance_timings_span_the_whole_turn(self):
        words = [
            self._word("one", "speaker_0", start=0.0, end=0.4),
            self._word(" ", type_="spacing"),
            self._word("two", "speaker_0", start=0.5, end=1.2),
        ]
        (utterance,) = _group_into_utterances(words)
        self.assertEqual(utterance.start, 0.0)
        self.assertEqual(utterance.end, 1.2)

    def test_missing_speaker_id_falls_back_rather_than_crashing(self):
        (utterance,) = _group_into_utterances([self._word("Hello")])
        self.assertEqual(utterance.speaker, "speaker_0")

    def test_empty_and_none_input(self):
        self.assertEqual(_group_into_utterances([]), [])
        self.assertEqual(_group_into_utterances(None), [])

    def test_spacing_only_input_produces_no_empty_utterances(self):
        self.assertEqual(_group_into_utterances([self._word(" ", type_="spacing")]), [])


class RoleInferenceTests(TestCase):
    def test_identifies_doctor_and_patient_in_a_typical_opening(self):
        utterances = _turns(
            ("speaker_0", "Hi. So what brought you in today?"),
            ("speaker_1", "I came in with some fatigue, and I noticed my skin is dry."),
            (
                "speaker_0",
                "I'm just looking at your blood results. I'd like to start you on medication.",
            ),
            ("speaker_1", "I haven't had that before."),
        )
        assignment = infer_roles(utterances)
        self.assertEqual(assignment.role_for("speaker_0"), DOCTOR)
        self.assertEqual(assignment.role_for("speaker_1"), PATIENT)
        self.assertEqual(assignment.confidence, "high")

    def test_roles_are_not_positional(self):
        """The patient speaking first must not make them the doctor."""
        utterances = _turns(
            ("speaker_0", "Doctor, I have chest pain and my heart races."),
            ("speaker_1", "I'd like to order a blood test. I'll send the prescription."),
        )
        assignment = infer_roles(utterances)
        self.assertEqual(assignment.role_for("speaker_0"), PATIENT)
        self.assertEqual(assignment.role_for("speaker_1"), DOCTOR)

    def test_refuses_to_guess_when_there_is_no_signal(self):
        utterances = _turns(("speaker_0", "Mm."), ("speaker_1", "Yeah."))
        assignment = infer_roles(utterances)
        self.assertEqual(assignment.confidence, "none")
        self.assertEqual(assignment.role_for("speaker_0"), UNKNOWN)
        self.assertEqual(assignment.role_for("speaker_1"), UNKNOWN)

    def test_single_speaker_describing_symptoms_reads_as_patient(self):
        utterances = _turns(
            ("speaker_0", "I am feeling chest pain and my posture is affected."),
        )
        assignment = infer_roles(utterances)
        self.assertEqual(assignment.role_for("speaker_0"), PATIENT)
        self.assertEqual(assignment.confidence, "low")

    def test_no_utterances(self):
        assignment = infer_roles([])
        self.assertEqual(assignment.confidence, "none")
        self.assertEqual(assignment.roles, {})

    def test_unknown_speaker_label_is_unknown(self):
        assignment = infer_roles(_turns(("speaker_0", "What brought you in today?")))
        self.assertEqual(assignment.role_for("speaker_9"), UNKNOWN)


class TranscriptTests(TestCase):
    def _transcript(self) -> Transcript:
        utterances = _turns(
            ("speaker_0", "What brought you in today? I'll send the prescription."),
            ("speaker_1", "I came in with fatigue and my skin is dry."),
        )
        return Transcript(
            text="full text",
            utterances=utterances,
            language_code="eng",
            roles=infer_roles(utterances),
        )

    def test_dialogue_uses_roles_by_default(self):
        dialogue = self._transcript().as_dialogue()
        self.assertIn("DOCTOR:", dialogue)
        self.assertIn("PATIENT:", dialogue)
        self.assertNotIn("speaker_0", dialogue)

    def test_raw_dialogue_keeps_diarization_labels(self):
        dialogue = self._transcript().as_dialogue(use_roles=False)
        self.assertIn("speaker_0:", dialogue)
        self.assertNotIn("DOCTOR:", dialogue)

    def test_dialogue_falls_back_to_labels_when_roles_unresolved(self):
        utterances = _turns(("speaker_0", "Mm."), ("speaker_1", "Yeah."))
        transcript = Transcript(
            text="",
            utterances=utterances,
            language_code="eng",
            roles=infer_roles(utterances),
        )
        self.assertIn("speaker_0:", transcript.as_dialogue())

    def test_transcript_without_role_inference_still_renders(self):
        transcript = Transcript(
            text="", utterances=_turns(("speaker_0", "Hello")), language_code="eng"
        )
        self.assertEqual(transcript.as_dialogue(), "speaker_0: Hello")

    def test_speakers_are_listed_in_first_heard_order(self):
        utterances = _turns(
            ("speaker_1", "first"), ("speaker_0", "second"), ("speaker_1", "again")
        )
        transcript = Transcript(text="", utterances=utterances, language_code="eng")
        self.assertEqual(transcript.speakers, ["speaker_1", "speaker_0"])

    def test_duration_is_the_last_end_timestamp(self):
        transcript = Transcript(
            text="",
            utterances=_turns(("speaker_0", "a"), ("speaker_1", "b")),
            language_code="eng",
        )
        self.assertAlmostEqual(transcript.duration, 1.9)

    def test_duration_is_none_without_timestamps(self):
        transcript = Transcript(
            text="",
            utterances=[Utterance("speaker_0", "hi", None, None)],
            language_code="eng",
        )
        self.assertIsNone(transcript.duration)


class DemoFixtureTests(TestCase):
    """Guards the committed demo transcript the later stages develop against.

    Re-running transcription costs money and minutes, so downstream work reads
    this file. If its shape drifts, those stages break silently — catch it here.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = json.loads(FIXTURE.read_text())

    def test_fixture_exists_and_is_valid_json(self):
        self.assertTrue(FIXTURE.is_file(), f"missing fixture: {FIXTURE}")
        self.assertIsInstance(self.data, dict)

    def test_has_the_keys_downstream_stages_read(self):
        for key in (
            "source_audio",
            "language_code",
            "duration_seconds",
            "role_confidence",
            "speakers",
            "dialogue",
            "utterances",
            "text",
        ):
            self.assertIn(key, self.data)

    def test_both_roles_were_resolved(self):
        roles = {s["role"] for s in self.data["speakers"]}
        self.assertEqual(roles, {DOCTOR, PATIENT})
        self.assertEqual(self.data["role_confidence"], "high")

    def test_every_turn_has_a_role_and_timestamps(self):
        for i, turn in enumerate(self.data["utterances"]):
            self.assertIn(turn["role"], (DOCTOR, PATIENT), f"turn {i}")
            self.assertIsNotNone(turn["start"], f"turn {i}")
            self.assertIsNotNone(turn["end"], f"turn {i}")
            self.assertGreaterEqual(turn["end"], turn["start"], f"turn {i}")

    def test_turns_are_in_chronological_order(self):
        starts = [t["start"] for t in self.data["utterances"]]
        self.assertEqual(starts, sorted(starts))

    def test_dialogue_has_one_line_per_turn(self):
        self.assertEqual(
            len(self.data["dialogue"].splitlines()),
            len(self.data["utterances"]),
        )

    def test_dialogue_is_role_labelled_not_raw(self):
        self.assertIn(f"{DOCTOR}:", self.data["dialogue"])
        self.assertIn(f"{PATIENT}:", self.data["dialogue"])
        self.assertNotIn("speaker_0:", self.data["dialogue"])

    def test_the_consultation_is_substantive_enough_to_summarise(self):
        """A near-empty transcript would make the summary stage look broken."""
        self.assertGreaterEqual(len(self.data["utterances"]), 10)
        self.assertGreater(self.data["duration_seconds"], 60)

