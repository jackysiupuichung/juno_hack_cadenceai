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

from capture import caretaker, medication, safety
from capture.caretaker import CaretakerContext
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


def _plan(items=(), schedule=(), goal="Establish whether the treatment has been started and tolerated."):
    """A plan built by hand.

    `build_plan` is a model call; nothing here may reach the network, and the
    arithmetic under test belongs to Python regardless of what the planner said.
    """
    from capture.plan import CheckInPlan

    return CheckInPlan(data={
        "interval_goal": goal,
        "items": list(items),
        "call_schedule": list(schedule),
        "reasoning": "hand-written for test",
    })


def _item(item_id, *, from_week=0, until_week=None, priority=2, intent=None,
          ask_directly=False):
    return {
        "id": item_id,
        "intent": intent or f"establish {item_id}",
        "why": "because the interval needs it",
        "from_week": from_week,
        "until_week": until_week,
        "priority": priority,
        "ask_directly": ask_directly,
        "commitment_ids": [],
        "context_ids": [],
    }


class PlanEligibilityTests(SimpleTestCase):
    """When an agenda item becomes askable is arithmetic, not judgement.

    The planner says which week an item is worth raising from; Python decides
    whether that week has arrived. Getting it wrong in either direction costs
    the same scarce thing — a question asked a week before it could possibly
    have an answer, or one that quietly never gets asked at all.
    """

    def test_an_item_is_not_due_before_its_from_week(self):
        plan = _plan([_item("blood_test", from_week=7)])
        self.assertEqual(plan.due_items(6), [])

    def test_an_item_is_due_on_the_exact_week_it_opens(self):
        """Off by one here is a question asked a week early, or never."""
        plan = _plan([_item("blood_test", from_week=7)])
        self.assertEqual([i["id"] for i in plan.due_items(7)], ["blood_test"])

    def test_an_item_with_no_until_week_stands_for_the_rest_of_the_interval(self):
        plan = _plan([_item("still_taking_it", from_week=1, until_week=None)])
        self.assertEqual([i["id"] for i in plan.due_items(52)], ["still_taking_it"])

    def test_an_until_week_retires_the_item_after_that_week(self):
        """Some questions stop being worth asking, and asking anyway is a cost."""
        plan = _plan([_item("early_side_effects", from_week=1, until_week=4)])
        self.assertEqual([i["id"] for i in plan.due_items(4)], ["early_side_effects"])
        self.assertEqual(plan.due_items(5), [])

    def test_a_week_before_the_interval_starts_is_due_for_nothing_scheduled_later(self):
        plan = _plan([_item("a", from_week=0), _item("b", from_week=2)])
        self.assertEqual([i["id"] for i in plan.due_items(0)], ["a"])

    def test_due_items_come_back_most_important_first(self):
        """A call has ten turns; they must be spent on priority 1 first."""
        plan = _plan([
            _item("nice_to_have", priority=3),
            _item("must_ask", priority=1),
            _item("worth_asking", priority=2),
        ])
        self.assertEqual([i["id"] for i in plan.due_items(3)],
                         ["must_ask", "worth_asking", "nice_to_have"])

    def test_an_empty_plan_is_due_for_nothing_rather_than_failing(self):
        self.assertEqual(_plan().due_items(4), [])


class NextCallWeekTests(SimpleTestCase):
    """The agent needs to know whether the interval continues past this call.

    Told there is another call coming, it can leave a thread for next time.
    Told there is not, it knows this is the last chance to ask before the
    appointment the brief is written for.
    """

    SCHEDULE = [
        {"week": 2, "focus": "started?", "item_ids": []},
        {"week": 7, "focus": "test done?", "item_ids": []},
        {"week": 12, "focus": "before the appointment", "item_ids": []},
    ]

    def test_it_returns_the_next_strictly_later_call(self):
        self.assertEqual(_plan(schedule=self.SCHEDULE).next_call_week(2), 7)

    def test_the_current_week_is_not_its_own_next_call(self):
        """Otherwise every call announces itself as the one still to come."""
        self.assertEqual(_plan(schedule=self.SCHEDULE).next_call_week(7), 12)

    def test_it_is_none_once_the_interval_has_no_further_calls(self):
        self.assertIsNone(_plan(schedule=self.SCHEDULE).next_call_week(12))

    def test_an_unscheduled_interval_has_no_next_call(self):
        self.assertIsNone(_plan().next_call_week(0))


class PlanCoverageTests(SimpleTestCase):
    """An unasked question must be reported, not silently dropped.

    This is the honesty guarantee the whole plan exists for. A doctor reading
    the brief takes absence as "nothing to report" — so a question that was on
    the agenda and never got asked has to say so by name. A gap reported plainly
    is useful; a gap left invisible is a claim the record cannot support.
    """

    PLAN = _plan([
        _item("blood_test", from_week=7, priority=1),
        _item("taking_it", from_week=1, priority=1),
        _item("late_review", from_week=20, priority=2),
    ])

    def test_a_due_item_nobody_covered_is_reported_as_missed(self):
        from capture.plan import coverage

        result = coverage(self.PLAN, covered=["taking_it"], week=8)
        self.assertEqual(result["missed"], ["blood_test"])

    def test_a_covered_item_is_recorded_as_covered(self):
        from capture.plan import coverage
        result = coverage(self.PLAN, covered=["taking_it", "blood_test"], week=8)
        self.assertEqual(sorted(result["covered"]), ["blood_test", "taking_it"])
        self.assertEqual(result["missed"], [])

    def test_an_item_that_was_not_yet_due_is_neither_covered_nor_missed(self):
        """Not asking about week 20 in week 8 is not a failure to report."""
        from capture.plan import coverage
        result = coverage(self.PLAN, covered=["taking_it"], week=8)
        self.assertNotIn("late_review", result["covered"])
        self.assertNotIn("late_review", result["missed"])
        self.assertEqual(result["not_yet_due"], ["late_review"])

    def test_every_planned_item_is_accounted_for_somewhere(self):
        """No item may vanish between the three buckets."""
        from capture.plan import coverage
        result = coverage(self.PLAN, covered=["blood_test"], week=8)
        placed = set(result["covered"]) | set(result["missed"]) | set(result["not_yet_due"])
        self.assertEqual(placed, {i["id"] for i in self.PLAN.items})

    def test_covering_something_that_was_never_planned_does_not_invent_coverage(self):
        from capture.plan import coverage
        result = coverage(self.PLAN, covered=["something_improvised"], week=8)
        self.assertEqual(sorted(result["missed"]), ["blood_test", "taking_it"])
        self.assertEqual(result["covered"], [])


class AgentBriefFromPlanTests(SimpleTestCase):
    """What the agent is allowed to see going into a call.

    The rendering is the enforcement point: an agent handed an item it cannot
    possibly have an answer for will ask about it anyway, and the patient is
    asked in week two whether they have had a blood test due in week seven.
    """

    def test_a_not_yet_due_item_never_reaches_the_agent(self):
        from capture.plan import as_agent_brief

        plan = _plan([
            _item("taking_it", from_week=1, intent="whether they started the tablet"),
            _item("blood_test", from_week=7, intent="whether the repeat blood test happened"),
        ])
        rendered = as_agent_brief(plan, week=2)
        self.assertIn("whether they started the tablet", rendered)
        self.assertNotIn("whether the repeat blood test happened", rendered)
        self.assertNotIn("[blood_test]", rendered)

    def test_the_agent_is_told_the_interval_continues_past_this_call(self):
        """So it does not force seven weeks of agenda into one tired call."""
        from capture.plan import as_agent_brief

        plan = _plan(
            [_item("taking_it", from_week=1), _item("blood_test", from_week=7)],
            schedule=[{"week": 7, "focus": "after the test", "item_ids": []}],
        )
        rendered = as_agent_brief(plan, week=2)
        self.assertIn("1 further item(s)", rendered)
        self.assertIn("week 7", rendered)

    def test_an_ask_directly_item_is_marked_as_one_the_patient_will_not_raise(self):
        from capture.plan import as_agent_brief

        plan = _plan([_item("palpitations", from_week=1, ask_directly=True)])
        self.assertIn("they will not raise it", as_agent_brief(plan, week=2))

    def test_a_planless_interval_renders_to_nothing_rather_than_a_stub(self):
        """An empty agenda block in the prompt reads as "there is nothing to ask"."""
        from capture.plan import as_agent_brief

        self.assertEqual(as_agent_brief(_plan(), week=3), "")


class TrajectoryWindowTests(SimpleTestCase):
    """Where the interval sits on the expected course — a position, not a verdict.

    The guideline's windows are wide and people fall outside them for reasons
    that have nothing to do with the treatment. So the only thing computed here
    is which side of the window today is on.
    """

    def _fact(self, today, event_id="early_symptom_change"):
        facts = _facts(today=today)
        return next(t for t in facts.trajectory if t.event["id"] == event_id)

    def test_before_the_earliest_week_it_is_too_early(self):
        # early_symptom_change opens at week 3; week 2 is before it.
        fact = self._fact(date(2026, 6, 15))
        self.assertEqual(fact.status, "too_early")
        self.assertEqual(fact.weeks_past_expected, 0)

    def test_the_earliest_week_itself_is_already_inside_the_window(self):
        fact = self._fact(date(2026, 6, 22))  # week 3
        self.assertEqual(fact.status, "in_window")

    def test_the_expected_by_week_itself_is_still_inside_the_window(self):
        """A marker is not late on the day it was expected by."""
        fact = self._fact(date(2026, 7, 27))  # week 8
        self.assertEqual(fact.status, "in_window")
        self.assertEqual(fact.weeks_past_expected, 0)

    def test_after_the_expected_week_it_is_past_expected_and_counted(self):
        fact = self._fact(date(2026, 8, 17))  # week 11
        self.assertEqual(fact.status, "past_expected")
        self.assertEqual(fact.weeks_past_expected, 3)

    def test_markers_that_are_still_too_early_are_reported_not_omitted(self):
        """"Nothing to say yet" and "no such milestone" are different facts."""
        facts = _facts(today=date(2026, 6, 15))
        self.assertEqual(len(facts.trajectory), 3)
        self.assertTrue(any(t.status == "too_early" for t in facts.trajectory))

    def test_markers_sit_at_different_points_of_the_same_interval(self):
        facts = _facts(today=date(2026, 8, 17))  # week 11
        by_id = {t.event["id"]: t.status for t in facts.trajectory}
        self.assertEqual(by_id["early_symptom_change"], "past_expected")
        self.assertEqual(by_id["full_symptom_resolution"], "in_window")
        self.assertEqual(by_id["biochemical_stability"], "too_early")


class TrajectoryObservationTests(SimpleTestCase):
    """Only a missed window is worth a line; being inside one is not news."""

    def test_nothing_is_said_about_a_marker_that_is_still_too_early(self):
        lines = observations(_facts(today=date(2026, 6, 15)))  # week 2
        self.assertFalse(any("No change in symptoms" in line for line in lines))

    def test_nothing_is_said_about_a_marker_inside_its_window(self):
        """Being on course is the ordinary case and needs no commentary."""
        lines = observations(_facts(today=date(2026, 7, 27)))  # week 8
        self.assertFalse(any("No change in symptoms" in line for line in lines))

    def test_a_marker_past_its_window_is_stated_with_both_dates(self):
        lines = observations(_facts(today=date(2026, 8, 17)))  # week 11
        line = next(l for l in lines if "No change in symptoms" in l)
        self.assertIn("by week 8", line)
        self.assertIn("it is now week 11", line)

    def test_the_context_wording_is_reproduced_rather_than_paraphrased(self):
        """Patient-facing clinical wording is never composed here."""
        source = next(t for t in load_context()["trajectory"]
                      if t["id"] == "early_symptom_change")
        lines = observations(_facts(today=date(2026, 8, 17)))
        self.assertTrue(any(source["if_not_met"].rstrip(". ") in l for l in lines))


class TrajectorySafetyTests(SimpleTestCase):
    """The line most likely to become a diagnosis is the one about the course.

    `safety.prohibited_outputs` names this exact failure — framing an
    expected-window shortfall as something being wrong. At a late week several
    markers have been missed at once, which is precisely when a sentence about
    "the treatment not working" would be most tempting and least supportable.
    Every line the interval produces there must pass the same filter the
    agent's own utterances do.
    """

    LATE = compute_interval_facts(
        summary=_summary(),
        context=load_context(),
        visit_date=date(2026, 1, 1),
        today=date(2026, 8, 1),
        prior_check_ins=[],
    )

    def test_the_late_week_really_does_have_several_missed_markers(self):
        """Otherwise the safety test below passes by having nothing to say."""
        self.assertEqual(self.LATE.week, 30)
        past = [t for t in self.LATE.trajectory if t.status == "past_expected"]
        self.assertEqual(len(past), 3)

    def test_every_line_produced_at_a_late_week_passes_the_safety_filter(self):
        for line in observations(self.LATE):
            self.assertEqual(safety.check_utterance(line), [], line)

    def test_no_trajectory_line_claims_the_treatment_is_failing(self):
        """A wide window missed is a fact about dates, not about the drug."""
        joined = " ".join(observations(self.LATE)).lower()
        for phrase in ("not working", "failing", "isn't working", "too high", "too low"):
            self.assertNotIn(phrase, joined)

    def test_every_if_not_met_line_in_the_context_survives_the_filter(self):
        """The context's own wording must pass the envelope it informs."""
        for event in load_context()["trajectory"]:
            line = (
                f"{event['if_not_met'].rstrip('. ')} — the usual window for this "
                f"is by week {event['expected_by_week']}, and it is now week 30."
            )
            self.assertEqual(safety.check_utterance(line), [], event["id"])


class CrossVisitTests(SimpleTestCase):
    """A second interval must know it is not the first — and the first must not pay.

    Almost every interval Cadence records is somebody's first, and that path
    has to stay exactly as cheap as it was before cross-visit context existed.
    When there is a previous brief, the opposite guarantee applies: the call
    must not open as though the patient had never been through any of this.
    """

    @staticmethod
    def _rendered(facts):
        from capture.interval import as_agent_brief

        return as_agent_brief(facts)

    PREVIOUS_BRIEF = {
        "agreed": [{"commitment_id": "c1", "text": "Start levothyroxine"}],
        "did": [
            {"commitment_id": "c1", "text": "Start levothyroxine", "status": "done"},
            {"commitment_id": "c2", "text": "Repeat blood test", "status": "not_done"},
        ],
        "happened": [{"text": "Sleep got worse", "approx_timing": "around week three"}],
        "changed": [{"text": "Tiredness eased a little", "direction": "better"}],
        "open_questions": ["Should I be taking it at night instead?"],
        "gaps": [],
    }

    def test_an_interval_with_no_previous_brief_behaves_exactly_as_before(self):
        """Every caller written before the loop closed still gets what it got."""
        facts = _facts(today=date(2026, 7, 20))
        self.assertIsNone(facts.previous_brief)
        self.assertEqual(facts.prior_visit_dates, [])
        self.assertNotIn("not their first interval", self._rendered(facts))

    def test_a_previous_brief_tells_the_agent_this_is_not_the_first_interval(self):
        facts = compute_interval_facts(
            summary=_summary(),
            context=load_context(),
            visit_date=VISIT,
            today=date(2026, 7, 20),
            previous_brief=self.PREVIOUS_BRIEF,
            prior_visit_dates=[date(2026, 3, 2)],
        )
        rendered = self._rendered(facts)
        self.assertIn("This is not their first interval.", rendered)
        self.assertIn("2026-03-02", rendered)

    def test_what_the_last_interval_left_unfinished_is_carried_forward(self):
        """A test not done last time is the first thing worth asking about."""
        facts = compute_interval_facts(
            summary=_summary(),
            context=load_context(),
            visit_date=VISIT,
            today=date(2026, 7, 20),
            previous_brief=self.PREVIOUS_BRIEF,
        )
        rendered = self._rendered(facts)
        self.assertIn("Repeat blood test", rendered)
        self.assertIn("Tiredness eased a little", rendered)
        self.assertIn("Should I be taking it at night instead?", rendered)

    def test_a_settled_commitment_from_last_time_is_not_carried_as_unfinished(self):
        facts = compute_interval_facts(
            summary=_summary(),
            context=load_context(),
            visit_date=VISIT,
            today=date(2026, 7, 20),
            previous_brief=self.PREVIOUS_BRIEF,
        )
        unfinished = next(
            l for l in self._rendered(facts).splitlines()
            if "Left unfinished last time" in l
        )
        self.assertNotIn("Start levothyroxine", unfinished)


class AttributedSpeechTests(SimpleTestCase):
    """Reading a consultation back is not the same act as making a claim.

    The visit chatbot's whole job is to hand the patient what was said at their
    appointment. "Your thyroid levels are low" is a diagnosis Cadence must never
    make; "your doctor said your thyroid levels are low" is a record of an
    appointment, and returning that record is the entire point of a patient-side
    scribe. The regexes cannot separate them, because the difference is the
    attribution and not the claim — so the exemption is opt-in per caller, and
    everything below fixes where its edges are.
    """

    ATTRIBUTED = [
        "Your doctor said your thyroid levels are low, which is why they started you on levothyroxine.",
        "The GP explained that your blood results came back showing an underactive thyroid.",
        "They told you your thyroid levels were low at the time of the appointment.",
        "Your consultant diagnosed hypothyroidism after your TSH results were high.",
        "Your doctor said your TSH levels are looking better than last time.",
        "Your doctor said your palpitations are caused by the tablets.",
        "The nurse mentioned your blood test was due around week seven.",
        "Your doctor said the treatment is working well so far.",
    ]

    ALWAYS_BLOCKED = [
        "The doctor said you should increase your dose.",
        "Your GP said you should book another blood test.",
    ]

    def test_a_clinical_statement_attributed_to_the_clinician_is_returnable(self):
        """This is the record the patient came for; refusing it is the failure."""
        for line in self.ATTRIBUTED:
            self.assertEqual(
                safety.check_utterance(line, allow_attributed=True), [], line
            )

    def test_the_same_sentences_are_still_blocked_without_the_flag(self):
        """The check-in agent composes live speech, so it never gets the exemption.

        Backwards compatibility is the guarantee: "the doctor said" from a mouth
        that was not in the room is a claim about a conversation it did not
        witness, not a quotation from a record.
        """
        for line in self.ATTRIBUTED:
            self.assertNotEqual(safety.check_utterance(line), [], line)

    def test_the_default_is_no_exemption_at_all(self):
        """Anything written before the flag existed keeps the behaviour it had."""
        line = self.ATTRIBUTED[0]
        self.assertEqual(
            safety.check_utterance(line), safety.check_utterance(line, allow_attributed=False)
        )

    def test_an_unattributed_test_result_is_blocked_even_with_the_flag_on(self):
        """The exemption keys on attribution being present, not on who asked."""
        self.assertEqual(
            safety.check_utterance("Your thyroid levels are low.", allow_attributed=True),
            ["interprets a test result"],
        )

    def test_an_unattributed_cause_is_blocked_even_with_the_flag_on(self):
        self.assertEqual(
            safety.check_utterance("That's because your dose is too high.", allow_attributed=True),
            ["attributes a cause to a symptom"],
        )

    def test_a_chatbot_that_slips_into_its_own_voice_is_still_caught(self):
        """The dangerous sentence is the one that drops the attribution."""
        for line in SafetyEnvelopeTests.PROHIBITED:
            self.assertNotEqual(
                safety.check_utterance(line, allow_attributed=True), [], line
            )

    def test_an_attributed_dose_change_is_still_blocked(self):
        """An invented instruction wearing the clinician's authority is worse.

        If the doctor really did say to increase the dose, it is in the record
        and the record is the safe place to read it from. If they did not, a
        fabricated instruction that arrives with "your doctor said" attached is
        far likelier to be acted on than a bare one — so attribution raises the
        stakes here rather than lowering them.
        """
        self.assertEqual(
            safety.check_utterance(
                "The doctor said you should increase your dose.", allow_attributed=True
            ),
            ["suggests a change to the dose or medication"],
        )

    def test_an_attributed_test_recommendation_is_still_blocked(self):
        """Same reasoning: an errand invented for the patient, signed by their GP."""
        self.assertEqual(
            safety.check_utterance(
                "Your GP said you should book another blood test.", allow_attributed=True
            ),
            ["recommends a test or referral the doctor did not raise"],
        )

    def test_both_always_blocked_prohibitions_survive_every_attribution(self):
        for line in self.ALWAYS_BLOCKED:
            self.assertNotEqual(
                safety.check_utterance(line, allow_attributed=True), [], line
            )

    def test_attribution_does_not_launder_a_line_that_breaks_two_rules(self):
        """The exempt reason drops out; the always-blocked one has to remain."""
        line = (
            "Your doctor said your TSH levels are too high, so you should "
            "increase your dose."
        )
        self.assertEqual(
            safety.check_utterance(line, allow_attributed=True),
            ["suggests a change to the dose or medication"],
        )

    def test_scrub_still_fails_closed_on_an_attributed_dose_change(self):
        """`scrub` never opts in, so the safe default reaches every legacy caller."""
        self.assertEqual(
            safety.scrub("The doctor said you should increase your dose."),
            safety.FALLBACK,
        )

    def test_empty_input_is_not_a_violation_with_the_flag_on_either(self):
        self.assertEqual(safety.check_utterance("", allow_attributed=True), [])
        self.assertEqual(safety.check_utterance("   ", allow_attributed=True), [])

    def test_no_benign_line_becomes_a_violation_when_the_flag_is_on(self):
        """Turning the exemption on may only ever remove reasons, never add them."""
        for line in SafetyEnvelopeTests.BENIGN:
            self.assertEqual(
                safety.check_utterance(line, allow_attributed=True), [], line
            )

    def test_every_patient_facing_red_flag_line_still_passes_with_the_flag_on(self):
        """The context's own warnings must survive both sides of the envelope."""
        for flag in load_context()["red_flags"]:
            line = f"{flag['patient_facing']} {flag['action']}"
            self.assertEqual(
                safety.check_utterance(line, allow_attributed=True), [], flag["id"]
            )


# --- The medication thread ------------------------------------------------
#
# Everything below is the second thread a consultation opens when it prescribes
# something. It runs on days rather than weeks and has its own sequence of
# failure points, none of them clinical: the prescription is never collected,
# the first dose is never taken, the label says something the patient was not
# told, the daily time is never set. What is tested here is that the thread
# reports each of those honestly and never fills a gap by inference — the one
# failure mode that would turn a record into a fabrication.


def _med(**overrides):
    """A medication with everything stated, so tests can remove one thing.

    Built complete and then broken deliberately: a test that starts from an
    empty medication proves nothing about which field it was that mattered.
    """
    from capture.medication import Medication, Source, Value

    base = dict(
        name=Value("Levothyroxine", Source.CLINICIAN),
        dosage=Value("25mcg", Source.CLINICIAN),
        frequency=Value("once daily", Source.CLINICIAN),
        duration=Value("ongoing", Source.CLINICIAN),
        instructions=Value("On an empty stomach", Source.CLINICIAN),
    )
    base.update(overrides)
    return Medication(**base)


class MedicationFromSummaryTests(SimpleTestCase):
    """What the consultation actually left behind, vagueness included."""

    def test_a_consultation_that_prescribed_nothing_opens_no_thread(self):
        """The brief is explicit: no prescription, no medication threads."""
        from capture.medication import from_summary

        self.assertEqual(from_summary({"medications": []}), [])
        self.assertEqual(from_summary({}), [])

    def test_every_field_from_the_visit_is_attributed_to_the_clinician(self):
        from capture.medication import Source, from_summary

        med = from_summary(_summary())[0]
        for field_name in ("name", "dosage", "frequency", "duration", "instructions"):
            self.assertIs(getattr(med, field_name).source, Source.CLINICIAN, field_name)

    def test_the_demo_consultations_very_low_dose_is_a_gap_not_a_dose(self):
        """The exact case the pharmacy label exists to resolve.

        "A very low dose" is authoritative — a doctor said it — and unusable:
        no reminder can be built from it. Both must be true at once, which is
        why provenance and stated-ness are separate questions.
        """
        from capture.medication import from_summary

        med = from_summary(_summary())[0]
        self.assertFalse(med.dosage.is_stated)
        self.assertIn("dosage", med.gaps)

    def test_a_qualifier_carrying_a_number_is_a_real_dose(self):
        """"Low dose, 25mcg" is stated; throwing it away would be the worse error."""
        from capture.medication import Source, Value

        self.assertTrue(Value("low dose, 25mcg", Source.CLINICIAN).is_stated)

    def test_the_summarisers_own_hedge_is_recognised_as_a_gap(self):
        from capture.medication import Source, Value

        hedge = Value("unclear — please confirm with your doctor", Source.CLINICIAN)
        self.assertFalse(hedge.is_stated)

    def test_an_empty_duration_is_not_a_reminder_gap(self):
        """Labels routinely omit it for a repeat; chasing a photo for it is noise."""
        from capture.medication import Source, Value

        med = _med(duration=Value("", Source.CLINICIAN))
        self.assertEqual(med.gaps, [])
        self.assertTrue(med.is_complete)


class MedicationLabelTests(SimpleTestCase):
    """The label fills gaps. It never overwrites, and never counts unconfirmed."""

    def test_a_label_fills_a_gap_the_consultation_left(self):
        from capture.medication import Source, Value, apply_label

        med = _med(dosage=Value("very low dose", Source.CLINICIAN))
        filled = apply_label(med, {"dosage": "25mcg"})
        self.assertEqual(filled.dosage.text, "25mcg")
        self.assertIs(filled.dosage.source, Source.LABEL)

    def test_a_label_never_overwrites_what_the_clinician_stated(self):
        """Silently preferring either side would hide a real discrepancy."""
        from capture.medication import apply_label

        filled = apply_label(_med(), {"dosage": "50mcg"})
        self.assertEqual(filled.dosage.text, "25mcg")

    def test_a_disagreement_is_recorded_for_the_patient_to_raise(self):
        from capture.medication import apply_label

        filled = apply_label(_med(), {"dosage": "50mcg"})
        note = " ".join(filled.notes)
        self.assertIn("50mcg", note)
        self.assertIn("25mcg", note)

    def test_a_label_value_is_pending_until_the_patient_agrees(self):
        """A misread label must not quietly become what they are told to take."""
        from capture.medication import Confirmation, Source, Value, apply_label

        med = _med(dosage=Value("", Source.CLINICIAN))
        filled = apply_label(med, {"dosage": "25mcg"})
        self.assertIs(filled.dosage.confirmation, Confirmation.PENDING)
        self.assertFalse(filled.dosage.is_usable)
        self.assertIn("dosage", filled.gaps)

    def test_confirming_makes_it_usable(self):
        from capture.medication import Source, Value, apply_label, confirm_label

        med = _med(dosage=Value("", Source.CLINICIAN))
        settled = confirm_label(apply_label(med, {"dosage": "25mcg"}), accepted=True)
        self.assertTrue(settled.dosage.is_usable)
        self.assertEqual(settled.gaps, [])

    def test_rejecting_reopens_the_gap_rather_than_keeping_a_wrong_value(self):
        """A value the patient says is wrong is worse than none: it looks filled."""
        from capture.medication import Source, Value, apply_label, confirm_label

        med = _med(dosage=Value("", Source.CLINICIAN))
        settled = confirm_label(apply_label(med, {"dosage": "25mcg"}), accepted=False)
        self.assertEqual(settled.dosage.text, "")
        self.assertIn("dosage", settled.gaps)

    def test_a_label_photo_is_only_asked_for_once_they_have_the_label(self):
        """A photo of a prescription still at the pharmacy does not exist."""
        from capture.medication import Collection, Source, Value

        med = _med(dosage=Value("", Source.CLINICIAN))
        self.assertFalse(replace_collection(med, Collection.NOT_COLLECTED).needs_label_photo)
        self.assertTrue(replace_collection(med, Collection.COLLECTED).needs_label_photo)

    def test_a_complete_medication_is_never_asked_for_a_photo(self):
        from capture.medication import Collection

        self.assertFalse(replace_collection(_med(), Collection.COLLECTED).needs_label_photo)


def replace_collection(med, collection):
    from dataclasses import replace

    return replace(med, collection=collection)


class MedicationAttributionTests(SimpleTestCase):
    """Three sources that must never be presented as each other."""

    def test_each_source_is_named_when_a_value_is_spoken(self):
        from capture.medication import Source, Value

        self.assertIn("your clinician", Value("25mcg", Source.CLINICIAN).attributed())
        self.assertIn("pharmacy label", Value("25mcg", Source.LABEL).attributed())
        self.assertIn("not from your clinician", Value("x", Source.GENERAL).attributed())

    def test_a_gap_is_reported_as_not_stated_rather_than_guessed_at(self):
        from capture.medication import Source, Value

        self.assertEqual(Value("", Source.CLINICIAN).attributed(), "not stated")


class MedicationTaskTests(SimpleTestCase):
    """Sequencing: nothing is asked before it could possibly have an answer."""

    def test_collection_is_the_only_thing_asked_before_it_is_collected(self):
        """Asking about doses and times first wastes the call on hypotheticals."""
        from capture.medication import due_tasks

        kinds = {t.kind for t in due_tasks([_med()], day=1)}
        self.assertEqual(kinds, {"collect"})

    def test_once_collected_the_first_dose_and_the_time_are_asked(self):
        from capture.medication import Collection, due_tasks

        med = replace_collection(_med(), Collection.COLLECTED)
        kinds = {t.kind for t in due_tasks([med], day=1)}
        self.assertIn("first_dose", kinds)
        self.assertIn("reminder_time", kinds)

    def test_chasing_a_collection_stops_before_it_becomes_nagging(self):
        from capture.medication import COLLECTION_CHASE_DAYS, due_tasks

        self.assertTrue(due_tasks([_med()], day=COLLECTION_CHASE_DAYS))
        self.assertEqual(due_tasks([_med()], day=COLLECTION_CHASE_DAYS + 1), [])

    def test_the_adherence_check_waits_for_something_to_report(self):
        from capture.medication import ADHERENCE_CHECK_DAYS, Collection, due_tasks
        from dataclasses import replace

        med = replace(
            _med(),
            collection=Collection.COLLECTED,
            first_dose_taken=True,
            reminder_time="07:30",
        )
        early = {t.kind for t in due_tasks([med], day=ADHERENCE_CHECK_DAYS - 1)}
        due = {t.kind for t in due_tasks([med], day=ADHERENCE_CHECK_DAYS)}
        self.assertNotIn("adherence", early)
        self.assertIn("adherence", due)

    def test_a_pending_label_is_read_back_rather_than_photographed_again(self):
        from capture.medication import (
            Collection, Source, Value, apply_label, due_tasks,
        )
        from dataclasses import replace

        med = replace(
            _med(dosage=Value("", Source.CLINICIAN)),
            collection=Collection.COLLECTED,
            first_dose_taken=True,
        )
        pending = apply_label(med, {"dosage": "25mcg"})
        kinds = {t.kind for t in due_tasks([pending], day=2)}
        self.assertIn("confirm_label", kinds)
        self.assertNotIn("label_photo", kinds)

    def test_nothing_prescribed_means_nothing_to_do(self):
        from capture.medication import due_tasks

        self.assertEqual(due_tasks([], day=1), [])


class DailyReminderTests(SimpleTestCase):
    """The daily nudge says only what it actually knows."""

    def _ready(self, **overrides):
        from dataclasses import replace

        return replace(_med(), reminder_time="07:30", **overrides)

    def test_a_reminder_names_the_dose_it_was_given(self):
        from capture.medication import daily_reminder

        line = daily_reminder(self._ready())
        self.assertIn("Levothyroxine", line)
        self.assertIn("25mcg", line)

    def test_the_clinicians_timing_instruction_is_attributed_to_them(self):
        from capture.medication import daily_reminder

        self.assertIn("Your clinician said", daily_reminder(self._ready()))

    def test_no_reminder_is_sent_while_a_gap_remains(self):
        """A reminder that cannot name the dose would have to invent one."""
        from capture.medication import Source, Value, daily_reminder

        self.assertEqual(daily_reminder(self._ready(dosage=Value("", Source.CLINICIAN))), "")

    def test_no_reminder_is_sent_before_a_time_is_chosen(self):
        from capture.medication import daily_reminder

        self.assertEqual(daily_reminder(_med()), "")

    def test_a_reminder_never_adds_a_timing_rule_the_clinician_did_not_give(self):
        from capture.medication import Source, Value, daily_reminder

        line = daily_reminder(self._ready(instructions=Value("", Source.CLINICIAN)))
        self.assertNotIn("clinician said", line)
        self.assertNotIn("empty stomach", line)

    def test_every_reminder_passes_the_safety_filter(self):
        """It names a drug and a dose, which is where that filter is strictest."""
        from capture.medication import daily_reminder

        self.assertEqual(safety.check_utterance(daily_reminder(self._ready())), [])


class MedicationObservationTests(SimpleTestCase):
    """Facts for the brief — the same no-conclusions contract as interval.py."""

    def test_a_missed_dose_is_reported_without_being_graded(self):
        from capture.medication import Adherence, observations
        from dataclasses import replace

        lines = observations([replace(_med(), adherence=Adherence.MISSED_MORE)])
        self.assertTrue(any("missing more than one dose" in l for l in lines))

    def test_an_unestablished_collection_is_distinguished_from_a_refusal(self):
        """"We never asked" and "they have not" are different facts."""
        from capture.medication import Collection, observations

        never = observations([replace_collection(_med(), Collection.UNKNOWN)])
        not_done = observations([replace_collection(_med(), Collection.NOT_COLLECTED)])
        self.assertTrue(any("Never established" in l for l in never))
        self.assertTrue(any("Not collected" in l for l in not_done))

    def test_every_observation_passes_the_safety_filter(self):
        from capture.medication import Adherence, Collection, observations
        from dataclasses import replace

        med = replace(
            _med(),
            collection=Collection.NOT_COLLECTED,
            first_dose_taken=False,
            adherence=Adherence.STOPPED,
        )
        for line in observations([med]):
            self.assertEqual(safety.check_utterance(line), [], line)

    def test_observations_of_the_demo_consultation_name_its_real_gap(self):
        from capture.medication import from_summary, observations

        lines = observations(from_summary(_summary()))
        self.assertTrue(any("did not state" in l and "dosage" in l for l in lines))


class MedicationAgentBriefTests(SimpleTestCase):
    """What the agent is shown, and what it must not be shown."""

    def test_an_interval_with_no_prescription_gets_no_medication_section(self):
        """An agent shown an empty heading will find something to ask about it."""
        from capture.medication import as_agent_brief

        self.assertEqual(as_agent_brief([], day=1), "")

    def test_a_gap_is_shown_as_a_gap_with_the_rule_against_inferring_it(self):
        from capture.medication import as_agent_brief, from_summary

        rendered = as_agent_brief(from_summary(_summary()), day=1)
        self.assertIn("not established", rendered)
        self.assertIn("never infer", rendered)

    def test_the_brief_shows_provenance_for_every_value(self):
        from capture.medication import as_agent_brief

        self.assertIn("as your clinician said", as_agent_brief([_med()], day=1))

    def test_tasks_are_rendered_as_aims_not_as_questions(self):
        """An agent handed sentences reads them out; the plan's rule holds here."""
        from capture.medication import as_agent_brief

        rendered = as_agent_brief([_med()], day=1)
        self.assertIn("aims, not questions", rendered)
        self.assertNotIn("?", rendered)


class FirstContactTests(SimpleTestCase):
    """Day one is a different call, not an early version of the same one."""

    def _prompt(self, day):
        from capture.checkin import _build_system_prompt
        from capture.medication import from_summary

        return _build_system_prompt(
            _facts(today=VISIT),
            load_context(),
            None,
            from_summary(_summary()),
            day,
        )

    def test_the_day_after_call_is_told_nothing_has_happened_yet(self):
        """The interval persona would ask a patient with no interval how it went."""
        prompt = self._prompt(1)
        self.assertIn("the day after their appointment", prompt)
        self.assertIn("Nothing has happened yet", prompt)

    def test_a_later_call_keeps_the_interval_persona(self):
        prompt = self._prompt(30)
        self.assertIn("phoning a patient between appointments", prompt)
        self.assertNotIn("Nothing has happened yet", prompt)

    def test_an_ordinary_check_in_with_no_day_is_unchanged(self):
        """Every caller written before first contact existed must still work."""
        prompt = self._prompt(None)
        self.assertIn("phoning a patient between appointments", prompt)

    def test_the_first_contact_call_must_not_end_without_the_reminder_time(self):
        """Everything downstream depends on it and nothing else will ask."""
        from capture.checkin import FIRST_CONTACT_FRAMING

        self.assertIn("do not end the call without it", FIRST_CONTACT_FRAMING)

    def test_both_personas_carry_the_same_boundary_rules(self):
        """A second copy of the safety rules is a second copy to drift."""
        from capture.checkin import FIRST_CONTACT_PROMPT, SHARED_RULES, SYSTEM_PROMPT

        self.assertIn(SHARED_RULES, SYSTEM_PROMPT)
        self.assertIn(SHARED_RULES, FIRST_CONTACT_PROMPT)
        self.assertIn("Never diagnose", FIRST_CONTACT_PROMPT)

    def test_explaining_the_clinician_is_permitted_and_answering_is_not(self):
        """The one place the brief is looser than the interval prompt was."""
        from capture.checkin import FIRST_CONTACT_PROMPT

        self.assertIn("plainer terms", FIRST_CONTACT_PROMPT)
        self.assertIn("one for their doctor", FIRST_CONTACT_PROMPT)

    def test_a_prescriptionless_consultation_gets_no_medication_section(self):
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=VISIT), load_context(), None, [], 1
        )
        self.assertNotIn("=== THE MEDICATION THREAD ===", prompt)

    def test_the_record_knows_which_call_was_the_first_contact(self):
        from capture.checkin import CheckIn

        empty = {"outcomes": [], "unprompted_reports": [], "questions_for_doctor": []}
        self.assertTrue(CheckIn(data=empty, day=1).is_first_contact)
        self.assertFalse(CheckIn(data=empty, day=14).is_first_contact)
        self.assertFalse(CheckIn(data=empty, day=None).is_first_contact)


class PlanDayEligibilityTests(SimpleTestCase):
    """Day-placed items are the first contact's; they must not leak into week 0.

    Both a day-1 item and a week-0 item are "week 0" by week arithmetic alone,
    and only one of them is worth asking on any given call. Getting this wrong
    puts "have you collected the prescription" into a week-six call, or drops it
    from day one entirely.
    """

    def test_a_from_day_item_is_due_on_its_day(self):
        plan = _plan([_item("collected", from_week=0)])
        plan.items[0]["from_day"] = 1
        self.assertEqual([i["id"] for i in plan.due_items(0, day=1)], ["collected"])

    def test_a_from_day_item_is_not_due_before_it(self):
        plan = _plan([_item("collected", from_week=0)])
        plan.items[0]["from_day"] = 1
        self.assertEqual(plan.due_items(0, day=0), [])

    def test_from_day_takes_precedence_over_from_week(self):
        """Otherwise from_week=0 makes it due on the day of the consultation."""
        plan = _plan([_item("collected", from_week=0)])
        plan.items[0]["from_day"] = 5
        self.assertEqual(plan.due_items(0, day=1), [])

    def test_a_week_only_caller_still_sees_from_day_items(self):
        """Day is derived from the week when absent, so nothing silently vanishes."""
        plan = _plan([_item("collected", from_week=0)])
        plan.items[0]["from_day"] = 1
        self.assertEqual([i["id"] for i in plan.due_items(2)], ["collected"])

    def test_an_until_week_still_retires_a_from_day_item(self):
        plan = _plan([_item("collected", from_week=0, until_week=2)])
        plan.items[0]["from_day"] = 1
        self.assertEqual([i["id"] for i in plan.due_items(2, day=14)], ["collected"])
        self.assertEqual(plan.due_items(3, day=21), [])

    def test_ordinary_week_items_are_untouched_by_the_day_arithmetic(self):
        plan = _plan([_item("blood_test", from_week=7)])
        self.assertEqual(plan.due_items(6), [])
        self.assertEqual([i["id"] for i in plan.due_items(7)], ["blood_test"])


class FirstContactScheduleTests(SimpleTestCase):
    """Finding the day-after call in a schedule that may not have one."""

    def test_a_day_placed_call_is_found_as_the_first_contact(self):
        plan = _plan(schedule=[
            {"week": 0, "day": 1, "focus": "confirm the plan", "item_ids": []},
            {"week": 2, "focus": "started?", "item_ids": []},
        ])
        self.assertEqual(plan.first_contact["focus"], "confirm the plan")

    def test_an_interval_that_planned_no_first_contact_has_none(self):
        """Not "the first entry" — that would pick up an ordinary week-two call."""
        plan = _plan(schedule=[{"week": 2, "focus": "started?", "item_ids": []}])
        self.assertIsNone(plan.first_contact)

    def test_the_day_after_call_gets_its_own_focus_not_week_zeros(self):
        from capture.plan import as_agent_brief

        plan = _plan(
            [_item("collected", from_week=0)],
            schedule=[
                {"week": 0, "day": 1, "focus": "confirm the plan is workable",
                 "item_ids": []},
                {"week": 0, "focus": "something else entirely", "item_ids": []},
            ],
        )
        rendered = as_agent_brief(plan, week=0, day=1)
        self.assertIn("confirm the plan is workable", rendered)
        self.assertNotIn("something else entirely", rendered)


class PlannerInputTests(SimpleTestCase):
    """What the planner is shown about medication and follow-up."""

    def test_a_prescriptionless_consultation_is_told_to_plan_no_med_items(self):
        from capture.plan import _drug_lines

        lines = _drug_lines({"medications": []}, load_context())
        self.assertIn("nothing was prescribed", lines)
        self.assertIn("no medication items", lines)

    def test_a_vague_dose_is_surfaced_to_the_planner_as_a_label_gap(self):
        from capture.plan import _drug_lines

        lines = _drug_lines(_summary(), load_context())
        self.assertIn("dosage", lines)
        self.assertIn("never something to infer", lines)

    def test_a_stated_follow_up_is_shown_with_what_to_do_about_it(self):
        from capture.plan import _follow_up_lines

        lines = _follow_up_lines(_summary())
        self.assertIn("three months", lines)
        self.assertIn("booked", lines)

    def test_an_absent_follow_up_is_stated_so_none_is_invented(self):
        from capture.plan import _follow_up_lines

        lines = _follow_up_lines({"future_plan": {"follow_up_needed": False}})
        self.assertIn("do not invent one", lines)


# --- Scored symptoms ------------------------------------------------------
#
# A number is only worth recording if it is comparable with the last one, which
# makes almost everything here a test about identity and honesty rather than
# about arithmetic: the same question every call, the same scale every tracker,
# and a visible gap wherever a number was asked for and not given. The
# arithmetic itself is subtraction, and the tests that matter are the ones
# holding the line between subtraction and a conclusion.


def _tracker(tracker_id="tiredness", **overrides):
    from capture.trackers import Tracker

    base = dict(
        id=tracker_id,
        label=tracker_id.replace("_", " ").capitalize(),
        question=f"How {tracker_id} have you felt this week?",
        context_id="original_symptoms",
        from_consultation=True,
    )
    base.update(overrides)
    return Tracker(**base)


def _series(values, tracker=None, weeks=None):
    """A series from a list of values; None entries are asked-but-unscored."""
    from capture.trackers import Score, Series

    tracker = tracker or _tracker()
    weeks = weeks or list(range(1, len(values) + 1))
    return Series(
        tracker=tracker,
        scores=[
            Score(tracker_id=tracker.id, week=w, value=v, patient_words="")
            for w, v in zip(weeks, values)
        ],
    )


class ScaleIdentityTests(SimpleTestCase):
    """The question and the scale must be identical every call, or the series lies."""

    def test_the_anchors_are_appended_so_they_cannot_drift_between_trackers(self):
        from capture.trackers import SCALE_ANCHOR

        asked = _tracker().asked()
        self.assertIn(SCALE_ANCHOR, asked)

    def test_a_question_that_already_states_the_scale_is_left_alone(self):
        """Otherwise the patient hears the anchors twice."""
        t = _tracker(question="Rate your tiredness from 1 to 10.")
        self.assertEqual(t.asked(), "Rate your tiredness from 1 to 10.")

    def test_the_anchors_name_ten_as_the_worst_end(self):
        """One direction system-wide: a reversed item is read backwards."""
        from capture.trackers import SCALE_ANCHOR

        self.assertIn("worst", SCALE_ANCHOR)


class SeriesArithmeticTests(SimpleTestCase):
    def test_delta_is_last_minus_first_and_positive_is_worse(self):
        self.assertEqual(_series([3, 7]).delta, 4)
        self.assertEqual(_series([7, 3]).delta, -4)

    def test_one_point_is_a_baseline_not_a_trend(self):
        self.assertIsNone(_series([5]).delta)
        self.assertEqual(_series([5]).direction, "unknown")

    def test_no_points_at_all_is_unknown_rather_than_steady(self):
        """"We have no numbers" must never render as "nothing changed"."""
        self.assertEqual(_series([]).direction, "unknown")

    def test_a_movement_inside_the_noise_band_is_not_called_a_change(self):
        from capture.trackers import MEANINGFUL_DELTA

        self.assertEqual(_series([5, 5 + MEANINGFUL_DELTA - 1]).direction, "steady")
        self.assertEqual(_series([5, 5 + MEANINGFUL_DELTA]).direction, "worse")

    def test_direction_reads_the_scale_the_right_way_round(self):
        self.assertEqual(_series([8, 2]).direction, "better")
        self.assertEqual(_series([2, 8]).direction, "worse")

    def test_the_sparkline_carries_the_week_of_every_point(self):
        """The calls are not evenly spaced; position alone misleads."""
        self.assertEqual(_series([6, 4, 3], weeks=[1, 3, 7]).sparkline(),
                         "wk1 6 → wk3 4 → wk7 3")

    def test_endpoints_are_the_first_and_last_scored_call_not_the_extremes(self):
        """A dip in the middle is not the story; where it started and ended is."""
        s = _series([6, 9, 4], weeks=[1, 3, 7])
        self.assertEqual(s.first.value, 6)
        self.assertEqual(s.last.value, 4)
        self.assertEqual(s.delta, -2)


class UnscoredAnswerTests(SimpleTestCase):
    """"Asked and got no number" and "never asked" are different facts."""

    def test_an_unscored_call_is_kept_as_a_visible_gap(self):
        s = _series([6, None, 3], weeks=[1, 3, 7])
        self.assertEqual([p.value for p in s.points], [6, 3])
        self.assertEqual(s.unscored_weeks, [3])

    def test_an_unscored_call_never_becomes_a_data_point(self):
        """Carrying the last score forward would draw a line nobody reported."""
        s = _series([6, None], weeks=[1, 3])
        self.assertEqual(len(s.points), 1)
        self.assertIsNone(s.delta)

    def test_the_patients_words_survive_when_the_number_does_not(self):
        from capture.trackers import Score, Series

        s = Series(tracker=_tracker(), scores=[
            Score(tracker_id="tiredness", week=3, value=None,
                  patient_words="about the same, I suppose"),
        ])
        self.assertEqual(s.points, [])
        self.assertIn("about the same", s.scores[0].patient_words)


class SeriesCollectionTests(SimpleTestCase):
    """Assembling the series from the interval's check-in records."""

    def _check_in(self, week, scores):
        return {"week": week, "symptom_scores": scores}

    def test_scores_are_gathered_across_calls_into_one_series(self):
        from capture.trackers import collect

        series = collect([_tracker()], [
            self._check_in(1, [{"tracker_id": "tiredness", "value": 6}]),
            self._check_in(7, [{"tracker_id": "tiredness", "value": 3}]),
        ])
        self.assertEqual(series[0].sparkline(), "wk1 6 → wk7 3")

    def test_a_score_for_an_unplanned_tracker_is_discarded(self):
        """A series nobody planned is not one the brief can read."""
        from capture.trackers import collect

        series = collect([_tracker()], [
            self._check_in(1, [{"tracker_id": "something_else", "value": 9}]),
        ])
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0].points, [])

    def test_a_tracker_nobody_ever_scored_still_gets_an_empty_series(self):
        """It has to appear in the brief as never rated, not vanish."""
        from capture.trackers import collect

        series = collect([_tracker()], [self._check_in(1, [])])
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0].points, [])

    def test_records_assembled_out_of_order_still_sort_by_week(self):
        from capture.trackers import collect

        series = collect([_tracker()], [
            self._check_in(7, [{"tracker_id": "tiredness", "value": 3}]),
            self._check_in(1, [{"tracker_id": "tiredness", "value": 6}]),
        ])
        self.assertEqual(series[0].sparkline(), "wk1 6 → wk7 3")

    def test_a_null_value_is_collected_as_unscored_rather_than_dropped(self):
        from capture.trackers import collect

        series = collect([_tracker()], [
            self._check_in(3, [{"tracker_id": "tiredness", "value": None,
                                "patient_words": "no idea"}]),
        ])
        self.assertEqual(series[0].unscored_weeks, [3])

    def test_the_week_in_a_meta_sidecar_is_understood(self):
        """run_check_in writes it there; the brief reads these files directly."""
        from capture.trackers import collect

        series = collect([_tracker()], [
            {"_meta": {"week": 4}, "symptom_scores": [
                {"tracker_id": "tiredness", "value": 5}]},
        ])
        self.assertEqual(series[0].points[0].week, 4)

    def test_an_interval_with_no_trackers_collects_nothing(self):
        from capture.trackers import collect

        self.assertEqual(collect([], [self._check_in(1, [])]), [])


class TrackerObservationTests(SimpleTestCase):
    """Lines the brief reproduces verbatim — numbers and weeks, no verdict."""

    def test_a_series_is_stated_with_its_points_and_its_endpoints(self):
        from capture.trackers import observations

        line = observations([_series([6, 3], weeks=[1, 7])])[0]
        self.assertIn("wk1 6 → wk7 3", line)
        self.assertIn("6 at week 1", line)
        self.assertIn("3 at week 7", line)

    def test_the_scale_direction_is_restated_so_it_cannot_be_read_backwards(self):
        from capture.trackers import observations

        self.assertIn("10 is worst", observations([_series([6, 3])])[0])

    def test_a_single_rating_says_there_is_nothing_to_compare_it_with(self):
        from capture.trackers import observations

        line = observations([_series([6])])[0]
        self.assertIn("Only one rating", line)

    def test_a_never_rated_tracker_is_reported_rather_than_omitted(self):
        from capture.trackers import observations

        self.assertIn("never rated", observations([_series([])])[0])

    def test_asked_but_never_answered_is_distinguished_from_never_asked(self):
        from capture.trackers import observations

        asked = observations([_series([None, None])])[0]
        self.assertIn("no rating was given", asked)
        self.assertNotIn("never rated", asked)

    def test_unscored_weeks_inside_a_series_are_named(self):
        from capture.trackers import observations

        lines = observations([_series([6, None, 3], weeks=[1, 3, 7])])
        self.assertTrue(any("week 3" in l and "no rating" in l for l in lines))

    def test_no_observation_draws_a_conclusion_from_the_movement(self):
        """The delta is subtraction; what it means is the doctor's.

        A four-point rise is exactly the material a reader editorialises, so the
        wording must offer nothing to build on — no "worsened", no "improved",
        no "significant", and nothing about the treatment.
        """
        from capture.trackers import observations

        joined = " ".join(observations([
            _series([2, 9], weeks=[1, 7]),
            _series([9, 2], weeks=[1, 7], tracker=_tracker("cold")),
        ])).lower()
        for word in ("worsen", "improv", "deteriorat", "significant", "concerning",
                     "responding", "working", "suggests", "indicates"):
            self.assertNotIn(word, joined)

    def test_every_observation_passes_the_safety_filter(self):
        from capture.trackers import observations

        for series in (_series([2, 9], weeks=[1, 7]), _series([9, 2]),
                       _series([5]), _series([]), _series([None])):
            for line in observations([series]):
                self.assertEqual(safety.check_utterance(line), [], line)


class TrackerAgentBriefTests(SimpleTestCase):
    """The one place the agent is told not to phrase things itself."""

    def test_the_verbatim_instruction_travels_with_the_questions(self):
        """Left in the standing prompt it loses to everything else about phrasing."""
        from capture.trackers import as_agent_brief

        rendered = as_agent_brief([_series([])], week=1)
        self.assertIn("EXACTLY as written", rendered)

    def test_the_question_is_rendered_with_its_anchors(self):
        from capture.trackers import SCALE_ANCHOR, as_agent_brief

        self.assertIn(SCALE_ANCHOR, as_agent_brief([_series([])], week=1))

    def test_prior_scores_are_shown_to_the_agent_but_marked_not_to_read_back(self):
        """An anchored patient repeats their last answer."""
        from capture.trackers import as_agent_brief

        rendered = as_agent_brief([_series([6], weeks=[1])], week=3)
        self.assertIn("wk1 6", rendered)
        self.assertIn("Do not read the earlier scores back", rendered)

    def test_the_agent_is_told_to_record_a_null_rather_than_estimate(self):
        from capture.trackers import as_agent_brief

        rendered = as_agent_brief([_series([])], week=1)
        self.assertIn("value null", rendered)
        self.assertIn("made-up number is worse than a gap", rendered)

    def test_an_interval_with_no_trackers_renders_to_nothing(self):
        """An empty heading is something for an agent to ask about."""
        from capture.trackers import as_agent_brief

        self.assertEqual(as_agent_brief([], week=3), "")


class TrackerChartDataTests(SimpleTestCase):
    def test_the_scale_travels_with_the_data_so_a_chart_cannot_invert_it(self):
        from capture.trackers import as_chart_data

        row = as_chart_data([_series([6, 3], weeks=[1, 7])])[0]
        self.assertEqual(row["scale"], {"min": 1, "max": 10, "high_is": "worst"})

    def test_unscored_weeks_are_reported_separately_from_the_points(self):
        from capture.trackers import as_chart_data

        row = as_chart_data([_series([6, None, 3], weeks=[1, 3, 7])])[0]
        self.assertEqual([p["week"] for p in row["points"]], [1, 7])
        self.assertEqual(row["asked_but_unscored_weeks"], [3])

    def test_no_interpretation_travels_with_the_chart_data(self):
        from capture.trackers import as_chart_data

        row = as_chart_data([_series([2, 9])])[0]
        self.assertEqual(set(row) & {"severity", "assessment", "concern", "verdict"},
                         set())


class TrackerPlanTests(SimpleTestCase):
    """The frozen set, as the planner writes it."""

    PLAN = {
        "tracked_symptoms": [
            {"id": "tiredness", "label": "Tiredness",
             "question": "How tired have you felt this week?",
             "context_id": "original_symptoms", "from_consultation": True},
        ]
    }

    def test_trackers_load_from_the_plan(self):
        from capture.trackers import from_plan

        t = from_plan(self.PLAN)[0]
        self.assertEqual(t.id, "tiredness")
        self.assertTrue(t.from_consultation)

    def test_a_plan_with_no_tracked_symptoms_yields_none(self):
        from capture.trackers import from_plan

        self.assertEqual(from_plan({}), [])

    def test_the_plan_object_exposes_what_it_froze(self):
        from capture.plan import CheckInPlan

        plan = CheckInPlan(data={**self.PLAN, "items": [], "call_schedule": [],
                                 "interval_goal": "", "reasoning": ""})
        self.assertEqual(len(plan.tracked_symptoms), 1)

    def test_the_planner_is_told_to_keep_ten_as_the_bad_end(self):
        """A reversed item is read backwards by everyone downstream."""
        from capture.plan import SYSTEM_PROMPT

        self.assertIn("10 is the bad end", SYSTEM_PROMPT)

    def test_the_planner_is_told_the_wording_is_frozen(self):
        from capture.plan import SYSTEM_PROMPT

        self.assertIn("asked verbatim", SYSTEM_PROMPT)


class ScoreCaptureTests(SimpleTestCase):
    """What a call is allowed to record, and what it does with a revision."""

    def test_the_turn_schema_constrains_a_rating_to_the_scale(self):
        from capture.checkin import load_schema
        from capture.trackers import SCALE_MAX, SCALE_MIN

        value = (load_schema()["properties"]["symptom_scores"]["items"]
                 ["properties"]["value"])
        self.assertEqual(value["minimum"], SCALE_MIN)
        self.assertEqual(value["maximum"], SCALE_MAX)

    def test_the_schema_permits_a_null_for_an_unanswered_rating(self):
        from capture.checkin import load_schema

        value = (load_schema()["properties"]["symptom_scores"]["items"]
                 ["properties"]["value"])
        self.assertIn("null", value["type"])

    def test_scores_are_kept_beside_the_schema_clean_record(self):
        """check_in.schema.json has nowhere for them, as with mentions."""
        from capture.checkin import CheckIn

        record = CheckIn(
            data={"outcomes": [], "unprompted_reports": [], "questions_for_doctor": []},
            symptom_scores=[{"tracker_id": "tiredness", "value": 4, "week": 3}],
        )
        self.assertEqual(len(record.symptom_scores), 1)
        self.assertNotIn("symptom_scores", record.data)

    def test_the_scored_questions_reach_the_agents_prompt(self):
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=date(2026, 7, 20)), load_context(), None, None, None,
            [_series([6], weeks=[1])],
        )
        self.assertIn("=== THE SCORED QUESTIONS ===", prompt)
        self.assertIn("EXACTLY as written", prompt)

    def test_an_interval_with_no_trackers_gets_no_scored_section(self):
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=date(2026, 7, 20)), load_context(), None, None, None, []
        )
        self.assertNotIn("=== THE SCORED QUESTIONS ===", prompt)


class CaretakerContextTests(SimpleTestCase):
    """The standing facts about the person, and what they do to a call."""

    def test_a_patient_nothing_is_known_about_renders_nothing(self):
        # Not a blank heading: an agent shown an empty section finds something
        # to do with it, which on a health call is a question nobody asked for.
        self.assertEqual(caretaker.as_agent_brief(CaretakerContext()), "")

    def test_a_context_with_only_a_call_preference_is_still_empty(self):
        # The preference always has a value, so counting it as content would
        # make every context non-empty and defeat the check entirely.
        self.assertTrue(CaretakerContext(call_length_preference="brief").is_empty)

    def test_the_preferred_name_is_what_the_agent_is_told_to_use(self):
        brief = caretaker.as_agent_brief(CaretakerContext(preferred_name="Marsh"))
        self.assertIn("Marsh", brief)

    def test_a_missing_preferred_name_falls_back_to_the_record(self):
        self.assertEqual(CaretakerContext().address_as("Marshall"), "Marshall")

    def test_with_neither_name_there_is_nothing_to_call_them(self):
        # "" rather than a placeholder, because a placeholder gets read aloud.
        self.assertEqual(CaretakerContext().address_as(), "")

    def test_call_length_governs_how_much_the_call_attempts(self):
        self.assertEqual(CaretakerContext(call_length_preference="brief").max_call_items, 2)
        self.assertEqual(CaretakerContext(call_length_preference="unhurried").max_call_items, 6)

    def test_an_unrecognised_preference_falls_back_rather_than_crashing(self):
        self.assertEqual(CaretakerContext(call_length_preference="???").max_call_items, 4)

    def test_medication_barriers_forbid_the_agent_solving_them(self):
        # The load-bearing one. An agent told "cannot swallow tablets" and left
        # alone suggests crushing them, which is a change to how medication is
        # taken — squarely across the CDS line this product does not cross.
        brief = caretaker.as_agent_brief(
            CaretakerContext(medication_barriers=["cannot swallow tablets"])
        )
        self.assertIn("cannot swallow tablets", brief)
        self.assertIn("Do not suggest a way around it", brief)

    def test_a_supporter_without_consent_is_marked_as_not_to_be_told(self):
        brief = caretaker.as_agent_brief(
            CaretakerContext(supporter_name="Ada", supporter_relationship="daughter")
        )
        self.assertIn("NOT agreed", brief)
        self.assertIn("Do not discuss their care", brief)

    def test_a_supporter_with_consent_says_so(self):
        brief = caretaker.as_agent_brief(
            CaretakerContext(
                supporter_name="Ada",
                supporter_relationship="daughter",
                supporter_may_be_contacted=True,
            )
        )
        self.assertIn("have agreed", brief)
        self.assertNotIn("NOT agreed", brief)

    def test_consent_cannot_be_stored_without_naming_the_person(self):
        # The failure this guards is disclosure to an unspecified third party:
        # a consent flag surviving the deletion of the name it referred to.
        row = caretaker.to_row(
            CaretakerContext(supporter_name="", supporter_may_be_contacted=True), "p1"
        )
        self.assertFalse(row["supporter_may_be_contacted"])

    def test_a_context_round_trips_through_a_row(self):
        original = CaretakerContext(
            preferred_name="Marsh",
            contact_window="after 2pm",
            call_length_preference="brief",
            living_situation="lives alone",
            access_needs=["hard of hearing"],
            medication_barriers=["cannot swallow tablets"],
            priorities=["being able to work"],
            supporter_name="Ada",
            supporter_relationship="daughter",
            supporter_may_be_contacted=True,
            notes="prefers text first",
        )
        self.assertEqual(caretaker.from_row(caretaker.to_row(original, "p1")), original)

    def test_a_missing_row_is_an_empty_context_not_a_crash(self):
        self.assertTrue(caretaker.from_row(None).is_empty)


class CaretakerPromptTests(SimpleTestCase):
    """Where the person appears in the agent's prompt, and when they do not."""

    def test_the_person_reaches_the_prompt(self):
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=date(2026, 7, 20)), load_context(), None, None, None, None,
            CaretakerContext(preferred_name="Marsh"),
        )
        self.assertIn("=== WHO YOU ARE SPEAKING TO ===", prompt)
        self.assertIn("Marsh", prompt)

    def test_the_person_is_stated_before_the_interval(self):
        # Who is being spoken to governs the whole call — how long to stay,
        # what to accommodate — so it must be read before the agenda has
        # already settled how the call will go.
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=date(2026, 7, 20)), load_context(), None, None, None, None,
            CaretakerContext(preferred_name="Marsh"),
        )
        self.assertLess(
            prompt.index("=== WHO YOU ARE SPEAKING TO ==="),
            prompt.index("=== THIS INTERVAL ==="),
        )

    def test_an_unknown_patient_gets_no_section(self):
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=date(2026, 7, 20)), load_context(), None, None, None, None,
            CaretakerContext(),
        )
        self.assertNotIn("=== WHO YOU ARE SPEAKING TO ===", prompt)

    def test_omitting_the_caretaker_entirely_behaves_as_before(self):
        from capture.checkin import _build_system_prompt

        prompt = _build_system_prompt(
            _facts(today=date(2026, 7, 20)), load_context(), None, None, None, None
        )
        self.assertNotIn("=== WHO YOU ARE SPEAKING TO ===", prompt)


class MedicationRowMappingTests(SimpleTestCase):
    """The row mapping. Where a medication thread would silently lose state.

    These matter because the mapping is the only thing standing between "the
    patient told us on Tuesday" and week 6 asking the same opening question for
    the sixth time. A field dropped here is invisible everywhere else.
    """

    def _med(self, **overrides):
        from capture.medication import Medication, Source, Value

        base = dict(
            name=Value("levothyroxine", Source.CLINICIAN),
            dosage=Value("25mcg", Source.CLINICIAN),
            frequency=Value("once daily", Source.CLINICIAN),
            duration=Value("", Source.CLINICIAN),
            instructions=Value("on an empty stomach", Source.CLINICIAN),
        )
        base.update(overrides)
        return Medication(**base)

    def test_a_medication_round_trips_through_a_row(self):
        from capture.medication import Adherence, Collection
        from loop.medication_repo import from_row, to_row

        original = self._med(
            collection=Collection.COLLECTED,
            first_dose_taken=True,
            reminder_time="07:30",
            adherence=Adherence.MISSED_ONCE,
            label_seen=True,
            last_chased_day=3,
            notes=["the label says 50mcg; your clinician said 25mcg"],
        )
        self.assertEqual(from_row(to_row(original, "v1")), original)

    def test_provenance_survives_the_round_trip(self):
        # The whole point of the type: a label value that comes back as a
        # clinician value is exactly the confusion Source exists to prevent.
        from capture.medication import Confirmation, Source, Value
        from loop.medication_repo import from_row, to_row

        original = self._med(
            dosage=Value("50mcg", Source.LABEL, Confirmation.PENDING)
        )
        restored = from_row(to_row(original, "v1"))
        self.assertEqual(restored.dosage.source, Source.LABEL)
        self.assertEqual(restored.dosage.confirmation, Confirmation.PENDING)
        self.assertFalse(restored.dosage.is_usable)

    def test_never_asked_and_answered_no_stay_different_facts(self):
        # Only one of these is worth reporting to a doctor. Collapsing the
        # tri-state would put a finding in the brief no patient ever said.
        from loop.medication_repo import from_row, to_row

        never = from_row(to_row(self._med(first_dose_taken=None), "v1"))
        said_no = from_row(to_row(self._med(first_dose_taken=False), "v1"))
        self.assertIsNone(never.first_dose_taken)
        self.assertIs(said_no.first_dose_taken, False)

    def test_a_gap_stays_a_gap(self):
        # Nothing in persistence completes a value the consultation left vague.
        from loop.medication_repo import from_row, to_row

        restored = from_row(to_row(self._med(), "v1"))
        self.assertFalse(restored.duration.is_stated)
        self.assertEqual(restored.duration.text, "")

    def test_an_unquantified_dose_round_trips_as_a_gap(self):
        from capture.medication import Source, Value
        from loop.medication_repo import from_row, to_row

        original = self._med(dosage=Value("a very low dose", Source.CLINICIAN))
        restored = from_row(to_row(original, "v1"))
        self.assertIn("dosage", restored.gaps)

    def test_an_empty_row_produces_a_medication_of_pure_gaps(self):
        # PostgREST omits nulls; every field defaulting is what stops a sparse
        # row becoming a crash mid-call.
        from loop.medication_repo import from_row

        restored = from_row({})
        self.assertEqual(restored.gaps, ["name", "dosage", "frequency"])
        self.assertFalse(restored.reminders_ready)


class SyntheticIntervalTests(SimpleTestCase):
    """The seeded 12-week interval, replayed without a database.

    seed_demo_interval writes this to Supabase, which cannot run here. What can
    run is everything that makes the fixture worth seeding: that its commitment
    texts match the summary it claims to be about, that its symptom mentions use
    phrases the disease context actually names, and that replaying its calls in
    order produces the medication thread and the fired cluster it says it does.

    A fixture that drifts from the schema it feeds is worse than no fixture: it
    seeds a demo that looks right and is not.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interval = json.loads((FIXTURES / "demo_interval.json").read_text())
        cls.summary = _summary()
        cls.context = load_context()

    def test_every_outcome_names_a_commitment_the_summary_actually_contains(self):
        # The join the seed does by text. A drifted string here means an outcome
        # silently skipped and a brief quietly missing a line.
        texts = {c["text"] for c in self.summary["commitments"]}
        for call in self.interval["check_ins"]:
            for outcome in call["raw"]["outcomes"]:
                self.assertIn(outcome["commitment_text"], texts)

    def test_every_mention_uses_a_phrase_the_context_names(self):
        # A phrase the context does not name cannot enter the vocabulary, so the
        # count downstream never sees it and the flag never fires.
        vocabulary = set(watch_for_vocabulary(self.context))
        for call in self.interval["check_ins"]:
            for mention in call["symptom_mentions"]:
                self.assertIn(mention["watch_for"], vocabulary)

    def test_every_mention_names_a_real_flag(self):
        flag_ids = {f["id"] for f in self.context["red_flags"]}
        for call in self.interval["check_ins"]:
            for mention in call["symptom_mentions"]:
                self.assertIn(mention["flag_id"], flag_ids)

    def test_the_calls_are_in_chronological_order(self):
        days = [c["day"] for c in self.interval["check_ins"]]
        self.assertEqual(days, sorted(days))

    def test_no_symptom_is_dated_after_the_call_that_reported_it(self):
        # occurred_at and recorded_at are separate for a reason; a symptom that
        # began after the call reporting it would be incoherent.
        for call in self.interval["check_ins"]:
            for event in call["events"]:
                self.assertLessEqual(event["occurred_at_day"], call["day"])

    def test_no_flag_fires_before_the_cluster_assembles(self):
        # One symptom is not a cluster. A fixture that fired at week 9 would be
        # demonstrating a false positive.
        mentions = []
        for call in self.interval["check_ins"]:
            if call["week"] >= 11:
                break
            mentions.extend({**m, "week": call["week"]} for m in call["symptom_mentions"])
        self.assertEqual(evaluate_flags(self.context, mentions, week=9), [])

    def test_the_cluster_assembles_by_the_end_of_the_interval(self):
        # The catch the product exists for: two signs, two weeks apart, neither
        # connected to the medication by the patient.
        mentions = []
        for call in self.interval["check_ins"]:
            mentions.extend({**m, "week": call["week"]} for m in call["symptom_mentions"])
        fired = evaluate_flags(self.context, mentions, week=11)
        self.assertIn(
            self.interval["expected_brief_shape"]["cluster"]["flag_id"],
            [f.flag_id for f in fired],
        )

    def test_the_cluster_is_built_from_more_than_one_call(self):
        weeks = {
            call["week"]
            for call in self.interval["check_ins"]
            if call["symptom_mentions"]
        }
        self.assertGreater(len(weeks), 1)


class VisitsHeldTests(SimpleTestCase):
    """An upcoming appointment must not be mistaken for the last consultation.

    Regression. list_visits sorts by date descending, so the moment a scheduled
    Visit 2 exists it comes back first — and every caller reaching for "the
    latest visit" got a row with no summary and no commitments. The brief came
    back with empty agreed[] and did[] and gaps claiming no commitments were
    recorded; the interval facts filtered out every check-in as predating it.
    Both looked like plausible output, which is what made it dangerous.
    """

    def _held(self, visits):
        from loop.views import _visits_held

        return _visits_held(visits)

    def test_an_appointment_ahead_is_not_the_latest_visit(self):
        upcoming = {"id": "next", "date": "2026-07-29", "summary": None}
        consultation = {"id": "held", "date": "2026-05-02", "summary": {"commitments": []}}
        self.assertEqual(
            [v["id"] for v in self._held([upcoming, consultation])], ["held"]
        )

    def test_a_consultation_recorded_today_still_counts_as_held(self):
        # Why the test is on the summary rather than the date: a visit recorded
        # this morning is in the past by seconds, and a date comparison would
        # have to decide what "today" means. Having been summarised is the
        # thing that actually distinguishes them.
        today = {"id": "today", "date": "2026-07-25", "summary": {"commitments": []}}
        self.assertEqual([v["id"] for v in self._held([today])], ["today"])

    def test_no_held_visit_is_distinguishable_from_no_visit_at_all(self):
        # A condition whose only row is an appointment ahead returns empty, so
        # callers report "nothing recorded yet" rather than building a brief
        # out of a visit that has not happened.
        self.assertEqual(self._held([{"id": "n", "date": "2026-07-29", "summary": None}]), [])


class SyntheticMedicationThreadTests(SimpleTestCase):
    """Replaying the interval's medication updates, call by call."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interval = json.loads((FIXTURES / "demo_interval.json").read_text())

    def _replay(self):
        from loop.management.commands.seed_demo_interval import Command

        command = Command()
        med = medication.from_summary(_summary())[0]
        for call in self.interval["check_ins"]:
            med = command._apply(med, call.get("medication_updates", {}))
        return med

    def test_the_consultation_leaves_the_dose_as_a_gap(self):
        # "a very low dose" is authoritative and unusable at the same time —
        # the exact case the label exists to resolve.
        med = medication.from_summary(_summary())[0]
        self.assertIn("dosage", med.gaps)

    def test_replaying_the_interval_closes_the_dose_gap(self):
        self.assertNotIn("dosage", self._replay().gaps)

    def test_the_label_disagreement_is_recorded_rather_than_resolved(self):
        # The clinician stated a frequency and the label prints a different one.
        # Cadence does not decide which is right; it hands the patient the
        # discrepancy to raise.
        med = self._replay()
        self.assertTrue(med.notes)
        self.assertTrue(any("label" in note.lower() for note in med.notes))

    def test_the_clinicians_own_words_are_never_overwritten_by_the_label(self):
        from capture.medication import Source

        med = self._replay()
        self.assertEqual(med.frequency.source, Source.CLINICIAN)

    def test_the_fixture_states_the_end_state_the_replay_actually_produces(self):
        # The fixture documents where the thread lands so a reviewer can check
        # it without running anything. That claim is worth nothing if it drifts
        # from the code, so it is asserted rather than trusted.
        from loop.medication_repo import to_row

        claimed = self.interval["medication_thread"]["expected_end_state"]
        actual = to_row(self._replay(), "v1")
        for field, expected in claimed.items():
            if field.startswith("_"):
                continue
            self.assertEqual(actual[field], expected, msg=f"field {field}")

    def test_the_thread_ends_ready_to_remind(self):
        # Fields plus a time. Without both, a reminder would have to name a dose
        # it does not know.
        self.assertTrue(self._replay().reminders_ready)

    def test_the_reminder_names_the_dose_the_label_gave(self):
        self.assertIn("25 micrograms", medication.daily_reminder(self._replay()))

    def test_adherence_is_current_state_not_interval_history(self):
        # The patient missed doses at week 5 and was back on it by week 9, so
        # the field says every_day — it is a snapshot, and the last call wins.
        # The missed fortnight is not lost: it lives in the events chronology,
        # dated when it happened rather than when it was mentioned. That split
        # is deliberate, and a brief that read adherence alone would miss it.
        from capture.medication import Adherence

        self.assertIs(self._replay().adherence, Adherence.EVERY_DAY)

    def test_the_missed_fortnight_survives_in_the_chronology(self):
        missed = [
            event
            for call in self.interval["check_ins"]
            for event in call["events"]
            if "missed" in event["label"].lower()
        ]
        self.assertTrue(missed)
        # Dated to when it happened, not to the call that surfaced it.
        self.assertLess(missed[0]["occurred_at_day"], 35)

    def test_observations_report_facts_rather_than_grading_them(self):
        lines = medication.observations([self._replay()])
        self.assertFalse(any("poor" in line.lower() for line in lines))
        self.assertFalse(any("good" in line.lower() for line in lines))

    def test_the_thread_accumulates_rather_than_resetting(self):
        # The bug the medications table was added to fix: without persistence
        # the thread rebuilds from the summary and week 12 knows nothing.
        replayed = self._replay()
        fresh = medication.from_summary(_summary())[0]
        self.assertNotEqual(replayed.collection, fresh.collection)
        self.assertTrue(replayed.reminder_time)
        self.assertFalse(fresh.reminder_time)
