"""Tests for the agent brain: interval facts, flag firing, and the safety net.

Everything here runs offline. The agent's reasoning needs a live model and is
exercised by `manage.py run_check_in`; what is tested here is the machinery the
reasoning is not allowed to be wrong about — how many weeks have passed,
whether a symptom cluster has actually assembled, and whether a sentence
crosses the line Cadence must not cross.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase

from capture import safety
from capture.interval import (
    IntervalError,
    commitment_id,
    compute_interval_facts,
    load_context,
    observations,
    watch_for_vocabulary,
)
from capture.redflags import evaluate_flags
from capture.simulate import ScriptedPatient

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

VISIT = date(2026, 6, 1)


def _summary() -> dict:
    body = json.loads((FIXTURES / "demo_consultation.summary.json").read_text())
    return body.get("summary", body)


def _facts(*, today, prior=()):
    return compute_interval_facts(
        summary=_summary(),
        context=load_context(),
        visit_date=VISIT,
        today=today,
        prior_check_ins=list(prior),
    )


class ContextLoadingTests(SimpleTestCase):
    def test_the_hypothyroidism_context_loads_and_is_complete(self):
        context = load_context("hypothyroidism")
        self.assertEqual(context["condition"]["id"], "hypothyroidism")
        for key in ("red_flags", "trajectory", "monitoring", "check_in_probes", "safety"):
            self.assertTrue(context[key], key)

    def test_an_unknown_condition_fails_loudly(self):
        with self.assertRaises(IntervalError):
            load_context("not_a_real_condition")

    def test_the_vocabulary_covers_every_watch_for_phrase(self):
        context = load_context()
        vocabulary = set(watch_for_vocabulary(context))
        for flag in context["red_flags"]:
            for phrase in flag["watch_for"]:
                self.assertIn(phrase, vocabulary)

    def test_the_vocabulary_has_no_duplicates(self):
        """It becomes a JSON Schema enum; duplicates would be invalid."""
        vocabulary = watch_for_vocabulary(load_context())
        self.assertEqual(len(vocabulary), len(set(vocabulary)))


class IntervalWeekTests(SimpleTestCase):
    def test_the_visit_day_itself_is_week_zero(self):
        self.assertEqual(_facts(today=VISIT).week, 0)

    def test_six_days_is_still_week_zero(self):
        self.assertEqual(_facts(today=date(2026, 6, 7)).week, 0)

    def test_seven_days_is_week_one(self):
        self.assertEqual(_facts(today=date(2026, 6, 8)).week, 1)

    def test_a_date_before_the_visit_clamps_to_zero_rather_than_going_negative(self):
        """A negative week would make every scheduled event look premature."""
        self.assertEqual(_facts(today=date(2026, 5, 1)).week, 0)


class CommitmentStatusTests(SimpleTestCase):
    def test_commitments_start_unknown_and_all_are_open(self):
        facts = _facts(today=date(2026, 7, 20))
        self.assertEqual(len(facts.commitments), 5)
        self.assertEqual(len(facts.open_commitments), 5)
        self.assertTrue(all(c.status == "unknown" for c in facts.commitments))

    def test_commitment_ids_are_positional_and_one_based(self):
        self.assertEqual(commitment_id(0), "c1")
        self.assertEqual(commitment_id(4), "c5")
        facts = _facts(today=VISIT)
        self.assertEqual([c.commitment_id for c in facts.commitments],
                         ["c1", "c2", "c3", "c4", "c5"])

    def test_a_done_outcome_settles_the_commitment(self):
        prior = [{"week": 2, "outcomes": [
            {"commitment_id": "c1", "status": "done",
             "patient_words": "started them", "note": ""}
        ]}]
        facts = _facts(today=date(2026, 7, 20), prior=prior)
        self.assertEqual(len(facts.open_commitments), 4)
        self.assertEqual([c.commitment_id for c in facts.settled_commitments], ["c1"])

    def test_a_later_check_in_supersedes_an_earlier_one(self):
        prior = [
            {"week": 2, "outcomes": [{"commitment_id": "c3", "status": "not_done",
                                      "patient_words": "not yet", "note": ""}]},
            {"week": 6, "outcomes": [{"commitment_id": "c3", "status": "done",
                                      "patient_words": "picked it up", "note": ""}]},
        ]
        facts = _facts(today=date(2026, 7, 20), prior=prior)
        c3 = next(c for c in facts.commitments if c.commitment_id == "c3")
        self.assertEqual(c3.status, "done")
        self.assertEqual(c3.last_asked_week, 6)

    def test_an_unknown_outcome_does_not_erase_an_earlier_answer(self):
        """Not discussing something on a later call is not a retraction."""
        prior = [
            {"week": 2, "outcomes": [{"commitment_id": "c1", "status": "done",
                                      "patient_words": "started", "note": ""}]},
            {"week": 6, "outcomes": [{"commitment_id": "c1", "status": "unknown",
                                      "patient_words": "", "note": ""}]},
        ]
        facts = _facts(today=date(2026, 7, 20), prior=prior)
        c1 = next(c for c in facts.commitments if c.commitment_id == "c1")
        self.assertEqual(c1.status, "done")
        self.assertEqual(c1.last_asked_week, 6)


class MonitoringTests(SimpleTestCase):
    def test_the_post_start_blood_test_is_due_at_week_seven(self):
        """NG145's 7-week repeat, anchored on the visit."""
        facts = _facts(today=date(2026, 7, 20))
        tft = next(m for m in facts.monitoring if m.event["id"] == "tft_after_start")
        self.assertEqual(tft.due_week, 7)
        self.assertEqual(facts.week, 7)

    def test_events_with_no_anchor_are_reported_unscheduled_not_overdue(self):
        """A dose change that never happened must not manufacture a due test."""
        facts = _facts(today=date(2026, 12, 1))
        for event_id in ("tft_after_dose_change", "tft_until_stable", "tft_annual"):
            fact = next(m for m in facts.monitoring if m.event["id"] == event_id)
            self.assertIsNone(fact.due_week, event_id)
            self.assertEqual(fact.weeks_overdue, 0, event_id)

    def test_the_grace_period_holds_before_calling_something_overdue(self):
        # Due week 7, grace 2 -> week 9 is still inside the window.
        facts = _facts(today=VISIT.replace(month=8, day=3))  # week 9
        tft = next(m for m in facts.monitoring if m.event["id"] == "tft_after_start")
        self.assertEqual(facts.week, 9)
        self.assertEqual(tft.weeks_overdue, 0)

    def test_past_the_grace_period_it_is_overdue(self):
        facts = _facts(today=date(2026, 8, 17))  # week 11
        tft = next(m for m in facts.monitoring if m.event["id"] == "tft_after_start")
        self.assertEqual(facts.week, 11)
        self.assertEqual(tft.weeks_overdue, 4)


class ObservationTests(SimpleTestCase):
    def test_an_overdue_test_is_reported_as_a_dated_fact(self):
        lines = observations(_facts(today=date(2026, 8, 17)))
        self.assertTrue(any("was due around week 7" in line for line in lines))

    def test_observations_never_interpret(self):
        """The line between reporting an interval and diagnosing one."""
        prior = [{"week": 2, "outcomes": [
            {"commitment_id": "c3", "status": "not_done",
             "patient_words": "not yet", "note": ""}]}]
        for line in observations(_facts(today=date(2026, 8, 17), prior=prior)):
            self.assertEqual(safety.check_utterance(line), [], line)

    def test_a_not_done_commitment_is_stated_plainly(self):
        prior = [{"week": 2, "outcomes": [
            {"commitment_id": "c3", "status": "not_done",
             "patient_words": "not yet", "note": ""}]}]
        lines = observations(_facts(today=date(2026, 7, 20), prior=prior))
        self.assertTrue(any(line.startswith("Not done:") for line in lines))


class RedFlagTests(SimpleTestCase):
    """The over-replacement cluster is the catch the product rests on."""

    def setUp(self):
        self.context = load_context()

    def _mention(self, phrase, week, flag="over_replacement_cluster"):
        return {"watch_for": phrase, "flag_id": flag,
                "patient_words": "...", "week": week}

    def test_one_sign_alone_does_not_fire_a_clustered_flag(self):
        mentions = [self._mention("trouble sleeping", 2)]
        self.assertEqual(evaluate_flags(self.context, mentions, week=2), [])

    def test_two_signs_fire_it_even_across_calls_weeks_apart(self):
        mentions = [
            self._mention("trouble sleeping", 2),
            self._mention("feeling hot when others do not, or sweating more", 6),
        ]
        fired = evaluate_flags(self.context, mentions, week=6)
        self.assertEqual([f.flag_id for f in fired], ["over_replacement_cluster"])
        self.assertEqual(fired[0].first_seen_week, 2)

    def test_the_same_sign_twice_is_still_one_sign(self):
        mentions = [
            self._mention("trouble sleeping", 2),
            self._mention("trouble sleeping", 5),
        ]
        self.assertEqual(evaluate_flags(self.context, mentions, week=5), [])

    def test_a_single_sign_flag_needs_no_cluster(self):
        mentions = [self._mention("chest pain", 4, flag="cardiac_over_replacement")]
        fired = evaluate_flags(self.context, mentions, week=4)
        self.assertEqual([f.flag_id for f in fired], ["cardiac_over_replacement"])

    def test_patient_facing_text_is_copied_verbatim_from_the_context(self):
        """Nothing patient-facing may be composed by a model."""
        mentions = [self._mention("chest pain", 4, flag="cardiac_over_replacement")]
        fired = evaluate_flags(self.context, mentions, week=4)[0]
        source = next(f for f in self.context["red_flags"]
                      if f["id"] == "cardiac_over_replacement")
        self.assertEqual(fired.patient_facing, source["patient_facing"])
        self.assertEqual(fired.action, source["action"])

    def test_emergencies_sort_ahead_of_same_day(self):
        mentions = [
            self._mention("trouble sleeping", 2),
            self._mention("feeling hot when others do not, or sweating more", 3),
            self._mention("chest pain", 6, flag="cardiac_over_replacement"),
        ]
        fired = evaluate_flags(self.context, mentions, week=6)
        self.assertEqual(fired[0].flag_id, "cardiac_over_replacement")

    def test_urgent_flags_interrupt_and_routine_ones_do_not(self):
        emergency = evaluate_flags(
            self.context,
            [self._mention("chest pain", 4, flag="cardiac_over_replacement")],
            week=4,
        )[0]
        self.assertTrue(emergency.interrupts)

        routine = next(f for f in self.context["red_flags"]
                       if f["urgency"] == "routine")
        fired = evaluate_flags(
            self.context,
            [self._mention(routine["watch_for"][0], 26, flag=routine["id"])],
            week=26,
        )
        self.assertFalse(fired[0].interrupts)

    def test_nothing_reported_fires_nothing(self):
        self.assertEqual(evaluate_flags(self.context, [], week=8), [])


class SafetyEnvelopeTests(SimpleTestCase):
    """The agent writes its own questions, so this is the last line."""

    PROHIBITED = [
        "You should increase your dose a little.",
        "It might be worth reducing the tablets.",
        "Stop the medication and see how you feel.",
        "That's probably because of the levothyroxine.",
        "Your palpitations are caused by the tablets.",
        "Your TSH levels are looking much better now.",
        "Your blood results came back normal.",
        "It sounds like the treatment isn't working.",
        "You should book a blood test.",
        "You need to ask for a referral.",
        "You should be feeling better by now.",
        "I think you have too much thyroid hormone.",
        "Try halving the tablet.",
        "That's a sign of over-treatment.",
        "Something is wrong here.",
        "Maybe skip a dose tomorrow.",
    ]

    BENIGN = [
        "How have you been getting on with the tablet each morning?",
        "Have you had your repeat blood test yet?",
        "Thanks, I have noted that down for your doctor.",
        "That's a good question for your doctor — I'll write it down.",
        "Since we last spoke, has anything new started?",
        "Have you noticed your heart racing or your hands feeling shaky?",
        "How has your sleep been?",
        "Your doctor asked for repeat bloods around week seven.",
        "Did you manage to pick up the prescription?",
        "Has your weight changed either way?",
        "Have things changed at all since we spoke?",
        "Are you still taking it first thing in the morning?",
        "Thanks for your time — take care.",
    ]

    def test_every_prohibited_line_is_caught(self):
        for line in self.PROHIBITED:
            self.assertNotEqual(safety.check_utterance(line), [], line)

    def test_no_benign_line_is_blocked(self):
        """An over-eager filter is its own failure — the call goes silent."""
        for line in self.BENIGN:
            self.assertEqual(safety.check_utterance(line), [], line)

    def test_scrub_replaces_a_violation_and_keeps_a_clean_line(self):
        self.assertEqual(safety.scrub(self.BENIGN[0]), self.BENIGN[0])
        self.assertEqual(safety.scrub("You should increase your dose."), safety.FALLBACK)

    def test_scrub_fails_closed_rather_than_raising(self):
        """A call that dies mid-sentence is worse than one that says less."""
        self.assertEqual(safety.scrub("Double the dose tonight."), safety.FALLBACK)

    def test_empty_input_is_not_a_violation(self):
        self.assertEqual(safety.check_utterance(""), [])
        self.assertEqual(safety.check_utterance("   "), [])

    def test_every_patient_facing_red_flag_line_passes_its_own_filter(self):
        """The context's own warnings must survive the envelope they inform."""
        for flag in load_context()["red_flags"]:
            line = f"{flag['patient_facing']} {flag['action']}"
            self.assertEqual(safety.check_utterance(line), [], flag["id"])


class CheckInRecordTests(SimpleTestCase):
    """The record a call leaves behind, which the next call and the brief read."""

    def test_symptom_mentions_survive_the_call(self):
        """They live beside `data`, not in it — and must not be dropped.

        A mention lost here is a cluster that never assembles: the symptom
        reported at week 2 has to still be there when its pair arrives weeks
        later, and check_in.schema.json has nowhere to keep it.
        """
        from capture.checkin import CheckIn

        record = CheckIn(
            data={"outcomes": [], "unprompted_reports": [], "questions_for_doctor": []},
            symptom_mentions=[
                {"watch_for": "trouble sleeping",
                 "flag_id": "over_replacement_cluster",
                 "patient_words": "not dropping off", "week": 2}
            ],
            week=2,
        )
        self.assertEqual(len(record.symptom_mentions), 1)
        self.assertNotIn("symptom_mentions", record.data)

    def test_the_data_body_matches_the_check_in_schema(self):
        """`data` is what gets persisted, so it must stay schema-clean."""
        from capture.checkin import CheckIn

        schema = json.loads(
            (Path(__file__).resolve().parents[2] / "schemas" / "check_in.schema.json").read_text()
        )
        record = CheckIn(
            data={"outcomes": [], "unprompted_reports": [], "questions_for_doctor": []}
        )
        self.assertEqual(set(record.data), set(schema["required"]))

    def test_mentions_feed_the_flag_evaluator_from_a_prior_interval(self):
        """A mention persisted at week 2 counts toward a week-6 cluster."""
        prior = [{
            "week": 2,
            "outcomes": [],
            "symptom_mentions": [{
                "watch_for": "trouble sleeping",
                "flag_id": "over_replacement_cluster",
                "patient_words": "not dropping off",
            }],
        }]
        facts = _facts(today=date(2026, 7, 20), prior=prior)
        self.assertEqual(len(facts.mentions), 1)
        self.assertEqual(facts.mentions[0].week, 2)

        carried = [
            {"watch_for": m.watch_for, "flag_id": m.flag_id,
             "patient_words": m.patient_words, "week": m.week}
            for m in facts.mentions
        ]
        this_call = [{
            "watch_for": "feeling hot when others do not, or sweating more",
            "flag_id": "over_replacement_cluster",
            "patient_words": "boiling at night", "week": 7,
        }]
        fired = evaluate_flags(load_context(), carried + this_call, week=7)
        self.assertEqual([f.flag_id for f in fired], ["over_replacement_cluster"])


class ScriptedPatientTests(SimpleTestCase):
    def test_the_first_matching_pattern_wins(self):
        patient = ScriptedPatient(replies=[
            (r"blood test", "Not yet, I keep forgetting."),
            (r"tablet", "Every morning, yes."),
        ])
        self.assertEqual(patient.respond("Have you had your blood test?"),
                         "Not yet, I keep forgetting.")
        self.assertEqual(patient.respond("How's the tablet going?"),
                         "Every morning, yes.")

    def test_an_unmatched_question_gets_the_default(self):
        patient = ScriptedPatient(replies=[(r"blood test", "No.")], default="Not sure.")
        self.assertEqual(patient.respond("How is your mood?"), "Not sure.")

    def test_matching_ignores_case_and_survives_rewording(self):
        """The agent writes its own questions, so scripts must be loose."""
        patient = ScriptedPatient(replies=[(r"sleep", "Badly, actually.")])
        self.assertEqual(patient.respond("And how has your SLEEP been lately?"),
                         "Badly, actually.")

    def test_it_records_what_it_was_asked(self):
        patient = ScriptedPatient(replies=[])
        patient.respond("First question?")
        patient.respond("Second question?")
        self.assertEqual(len(patient.said), 2)
