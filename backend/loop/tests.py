"""Tests for loop.auth (the one part of the account system that doesn't touch
Supabase, so it's covered by unit tests here rather than by hand against the
live database) and for the condition-scoped chatbot in loop.views.

The chatbot tests stub the repo and the LLM. The point is not to test
Supabase or Claude but the two things this app actually decides: what goes
into the record the model reads, and what comes back out past the safety
backstop.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from . import auth, views


class PasswordHashingTests(SimpleTestCase):
    def test_round_trip(self):
        hashed = auth.hash_password("correct horse battery staple")
        self.assertTrue(auth.verify_password("correct horse battery staple", hashed))

    def test_wrong_password_rejected(self):
        hashed = auth.hash_password("correct horse battery staple")
        self.assertFalse(auth.verify_password("wrong password", hashed))

    def test_hash_is_not_the_plaintext(self):
        hashed = auth.hash_password("hunter2")
        self.assertNotEqual(hashed, "hunter2")


class TokenTests(SimpleTestCase):
    def test_round_trip(self):
        token = auth.issue_token("patient-123")
        self.assertEqual(auth.decode_token(token), "patient-123")

    def test_refuses_to_sign_with_the_public_dev_default(self):
        with patch.object(auth.settings, "SECRET_KEY", auth._INSECURE_DEFAULT_KEY):
            with self.assertRaises(RuntimeError):
                auth.issue_token("patient-123")

    def test_tampered_token_rejected(self):
        token = auth.issue_token("patient-123")
        self.assertIsNone(auth.decode_token(token + "x"))

    def test_garbage_rejected(self):
        self.assertIsNone(auth.decode_token("not-a-token"))

    def test_expired_token_rejected(self):
        with patch.object(auth, "TOKEN_TTL_SECONDS", -1):
            token = auth.issue_token("patient-123")
        self.assertIsNone(auth.decode_token(token))


class PatientIdFromRequestTests(SimpleTestCase):
    def _request(self, header: str | None) -> Request:
        factory = APIRequestFactory()
        extra = {"HTTP_AUTHORIZATION": header} if header else {}
        return Request(factory.get("/", **extra))

    def test_missing_header(self):
        self.assertIsNone(auth.patient_id_from_request(self._request(None)))

    def test_malformed_header(self):
        self.assertIsNone(auth.patient_id_from_request(self._request("Token abc")))

    def test_valid_bearer_token(self):
        token = auth.issue_token("patient-456")
        request = self._request(f"Bearer {token}")
        self.assertEqual(auth.patient_id_from_request(request), "patient-456")


class ConditionRecordTests(TestCase):
    """What _condition_record puts in front of the model.

    Everything here stubs the repo and the LLM. The point is not to test
    Supabase or Claude but the two things this app actually decides: what
    goes into the record the model reads, and what comes back out past the
    safety backstop.

    The record-assembly tests matter more than they look. A patient asking
    "am I still meant to be taking this" gets a wrong and confidently-stated
    answer if the assembler quietly drops a later appointment, and no amount
    of prompt care recovers from a fact that was never in the context.
    """

    def setUp(self):
        self.visits = [
            {
                "id": "v2",
                "date": "2026-03-04",
                "care_setting": "gp",
                "clinician_name": "Dr Bell",
                "summary": {"doctor_diagnosis": "dose raised"},
                "transcript": "raise it to 75",
            },
            {
                "id": "v1",
                "date": "2026-01-10",
                "care_setting": "gp",
                "clinician_name": "Dr Bell",
                "summary": {"doctor_diagnosis": "started"},
                "transcript": "start 50",
            },
        ]

    def _record(self, **overrides):
        stubs = {
            "list_visits": lambda cid: self.visits,
            "get_commitments_for_visit": lambda vid: [],
            "list_check_ins": lambda cid: [],
            "list_events": lambda cid: [],
        }
        stubs.update(overrides)
        with patch.multiple("loop.views.repo", **{k: staticmethod(v) for k, v in stubs.items()}), \
             patch("loop.views.medication_repo.list_medications", return_value=[]):
            return views._condition_record("c1")

    def test_every_consultation_is_present(self):
        """Not just the latest — the whole point is the record spans visits."""
        record = self._record()
        self.assertEqual([c["id"] for c in record["consultations"]], ["v2", "v1"])

    def test_consultations_are_newest_first(self):
        """A superseded instruction reported as current is the worst failure
        this endpoint has; current state leads."""
        record = self._record()
        dates = [c["date"] for c in record["consultations"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_transcripts_are_included(self):
        """The summary is a lossy read; questions about what was said need the
        words."""
        record = self._record()
        self.assertEqual(record["consultations"][0]["transcript"], "raise it to 75")

    def test_agreed_commitments_are_attached_to_their_visit(self):
        commitments = {
            "v2": [{"id": "x", "text": "repeat bloods", "type": "test",
                    "timeframe": "6 weeks", "status": "open"}],
            "v1": [],
        }
        record = self._record(get_commitments_for_visit=lambda vid: commitments[vid])
        self.assertEqual(record["consultations"][0]["agreed"][0]["text"], "repeat bloods")
        self.assertEqual(record["consultations"][1]["agreed"], [])

    def test_patient_reports_are_kept_separate_from_clinical_record(self):
        """The prompt forbids restating a patient report as a clinical finding.
        This is the structure that makes the two distinguishable at all."""
        check_ins = [{
            "date": "2026-04-12",
            "outcomes": [{"status": "not_done", "patient_words": "dizzy again", "note": ""}],
            "raw": {"questions_for_doctor": ["is this normal?"]},
        }]
        record = self._record(list_check_ins=lambda cid: check_ins)
        self.assertNotIn("dizzy again", str(record["consultations"]))
        reported = record["check_ins_patient_reported"][0]
        self.assertEqual(reported["patient_reported"][0]["patient_words"], "dizzy again")
        self.assertEqual(reported["questions_for_doctor"], ["is this normal?"])

    def test_empty_sections_are_omitted_not_sent_empty(self):
        record = self._record()
        for key in ("medications", "check_ins_patient_reported", "chronology"):
            self.assertNotIn(key, record)

    def test_medications_are_included_when_present(self):
        meds = [{"id": "m1", "name": "levothyroxine", "dosage": "75mcg"}]
        with patch.multiple(
            "loop.views.repo",
            list_visits=staticmethod(lambda cid: self.visits),
            get_commitments_for_visit=staticmethod(lambda vid: []),
            list_check_ins=staticmethod(lambda cid: []),
            list_events=staticmethod(lambda cid: []),
        ), patch("loop.views.medication_repo.list_medications", return_value=meds):
            record = views._condition_record("c1")
        self.assertEqual(record["medications"], meds)


class AskEndpointTests(TestCase):
    """What comes back out of POST /api/ask."""

    def setUp(self):
        self.token = auth.issue_token("patient-1")

    def _post(self, body):
        return self.client.post(
            "/api/ask", body, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

    def test_question_alone_is_rejected(self):
        self.assertEqual(self._post({"question": "what now?"}).status_code, 400)

    def test_scope_alone_is_rejected(self):
        self.assertEqual(self._post({"condition_id": "c1"}).status_code, 400)

    def test_unknown_condition_is_404(self):
        with patch("loop.views.repo.get_condition", return_value=None):
            res = self._post({"condition_id": "c1", "question": "what now?"})
        self.assertEqual(res.status_code, 404)

    def test_condition_with_no_consultations_answers_without_calling_the_model(self):
        """Nothing recorded is a real state, and it deserves a plain answer
        rather than a model invited to invent one."""
        with patch("loop.views.repo.get_condition",
                   return_value={"id": "c1", "name": "Thyroid", "patient_id": "patient-1"}), \
             patch("loop.views._condition_record", return_value={"consultations": []}), \
             patch("loop.views.call_llm_json") as llm:
            res = self._post({"condition_id": "c1", "question": "what now?"})
        llm.assert_not_called()
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["grounded"])

    def test_grounded_answer_passes_through_with_sources(self):
        answer = {"answer": "Your doctor said to take 75mcg.", "grounded": True,
                  "sources": ["appointment 4 Mar"]}
        with patch("loop.views.repo.get_condition",
                   return_value={"id": "c1", "name": "Thyroid", "patient_id": "patient-1"}), \
             patch("loop.views._condition_record", return_value={"consultations": [{"id": "v2"}]}), \
             patch("loop.views.call_llm_json", return_value=answer), \
             patch("loop.views.safety.check_utterance", return_value=[]):
            res = self._post({"condition_id": "c1", "question": "what am I taking?"})
        self.assertEqual(res.json()["sources"], ["appointment 4 Mar"])
        self.assertTrue(res.json()["grounded"])

    def test_unsafe_answer_is_withheld_and_loses_its_citations(self):
        """Citations under a refusal would imply the record produced it."""
        unsafe = {"answer": "You should double your dose.", "grounded": True,
                  "sources": ["appointment 4 Mar"]}
        with patch("loop.views.repo.get_condition",
                   return_value={"id": "c1", "name": "Thyroid", "patient_id": "patient-1"}), \
             patch("loop.views._condition_record", return_value={"consultations": [{"id": "v2"}]}), \
             patch("loop.views.call_llm_json", return_value=unsafe), \
             patch("loop.views.safety.check_utterance",
                   return_value=["suggests a change to the dose or medication"]):
            body = self._post({"condition_id": "c1", "question": "should I take more?"}).json()
        self.assertTrue(body["withheld"])
        self.assertFalse(body["grounded"])
        self.assertEqual(body["sources"], [])
        self.assertNotIn("double", body["answer"])

    def test_visit_scope_still_works(self):
        """The single-visit chatbot predates this and is still wired up."""
        visit = {"id": "v1", "transcript": "start 50", "summary": {}, "patient_id": "patient-1"}
        with patch("loop.views.repo.get_visit", return_value=visit), \
             patch("loop.views.call_llm_json", return_value={"answer": "50mcg.", "grounded": True}) as llm, \
             patch("loop.views.safety.check_utterance", return_value=[]):
            res = self._post({"visit_id": "v1", "question": "what dose?"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(llm.call_args[0][0], views.QA_SYSTEM_PROMPT)

    def test_visit_scope_is_normalised_to_the_shared_shape(self):
        """The visit prompt's schema has no "sources"; the endpoint fills it in
        so the frontend never branches on which scope answered."""
        visit = {"id": "v1", "transcript": "start 50", "summary": {}, "patient_id": "patient-1"}
        with patch("loop.views.repo.get_visit", return_value=visit), \
             patch("loop.views.call_llm_json", return_value={"answer": "50mcg.", "grounded": True}), \
             patch("loop.views.safety.check_utterance", return_value=[]):
            body = self._post({"visit_id": "v1", "question": "what dose?"}).json()
        self.assertEqual(body["sources"], [])

    def test_condition_scope_uses_the_condition_prompt(self):
        with patch("loop.views.repo.get_condition",
                   return_value={"id": "c1", "name": "Thyroid", "patient_id": "patient-1"}), \
             patch("loop.views._condition_record", return_value={"consultations": [{"id": "v2"}]}), \
             patch("loop.views.call_llm_json", return_value={"answer": "x", "grounded": True}) as llm, \
             patch("loop.views.safety.check_utterance", return_value=[]):
            self._post({"condition_id": "c1", "question": "what am I taking?"})
        self.assertEqual(llm.call_args[0][0], views.CONDITION_QA_SYSTEM_PROMPT)
