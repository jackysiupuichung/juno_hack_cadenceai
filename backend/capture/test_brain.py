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
