# tests/test_briefs.py
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import briefs

GOOD = json.dumps([{"id": "abc", "gist": "Write a 500-word response to the Degas reading.",
                    "steps": [{"name": "read the piece", "minutes": 40}, {"name": "outline", "minutes": 20},
                              {"name": "write", "minutes": 60}],
                    "watchOut": ["due Tuesday, discussed Thursday"]}])


class ValidateTests(unittest.TestCase):
    def test_good_row_is_kept_and_trimmed(self):
        out = briefs.validate(GOOD)
        self.assertEqual(set(out), {"abc"})
        b = out["abc"]
        self.assertEqual(b["gist"], "Write a 500-word response to the Degas reading.")
        self.assertEqual([s["minutes"] for s in b["steps"]], [40, 20, 60])
        self.assertEqual(b["watchOut"], ["due Tuesday, discussed Thursday"])

    def test_bad_shapes_are_dropped(self):
        raw = json.dumps([{"id": "x", "gist": "", "steps": []},                 # no gist, no steps
                          {"id": "y", "gist": "ok", "steps": [{"name": "a"}]},  # minutes missing
                          {"gist": "no id", "steps": [{"name": "a", "minutes": 5}]}])
        self.assertEqual(briefs.validate(raw), {})

    def test_code_fence_and_prose_around_json_are_tolerated(self):
        self.assertIn("abc", briefs.validate("Sure:\n```json\n" + GOOD + "\n```\n"))

    def test_steps_capped_at_seven_and_minutes_clamped(self):
        rows = [{"id": "z", "gist": "g", "steps": [{"name": "s%d" % i, "minutes": 5000} for i in range(9)]}]
        b = briefs.validate(json.dumps(rows))["z"]
        self.assertEqual(len(b["steps"]), briefs.MAX_STEPS)
        self.assertEqual(b["steps"][0]["minutes"], 240)


class DueTests(unittest.TestCase):
    def test_utc_due_is_shown_as_her_local_day(self):
        self.assertEqual(briefs._local_due("2026-09-29T03:59:00Z"), "Mon 2026-09-28 23:59")
        self.assertEqual(briefs._local_due("2026-10-06T19:00:00"), "Tue 2026-10-06 19:00")


class WatchTests(unittest.TestCase):
    def test_warnings_doubting_the_due_date_are_dropped(self):
        raw = json.dumps([{"id": "w", "gist": "g", "steps": [{"name": "a", "minutes": 10}], "watchOut": [
            "Confirm which date counts on the schedule sheet.",
            "Is Sept 28 the due or assigned date?",
            "Quiz 3 (Lessons 4, 5) is due the same day."]}])
        self.assertEqual(briefs.validate(raw)["w"]["watchOut"], ["Quiz 3 (Lessons 4, 5) is due the same day."])


class HowTests(unittest.TestCase):
    def test_step_keeps_its_how(self):
        raw = json.dumps([{"id": "h", "gist": "g", "steps": [
            {"name": "Review Lesson 6: mean, SD", "how": "Redo the two worked examples on slide 12 first.", "minutes": 20},
            {"name": "Do problems 1-4", "minutes": 40}]}])
        steps = briefs.validate(raw)["h"]["steps"]
        self.assertEqual(steps[0]["how"], "Redo the two worked examples on slide 12 first.")
        self.assertNotIn("how", steps[1])


class PromptTests(unittest.TestCase):
    def test_prompt_carries_gathered_evidence(self):
        item = {"id": "m3", "course": "Math", "title": "Homework 3 (6, 7)", "due": "2026-09-28",
                "context": "schedule sheet: Lesson 6 - Measures of Center and Variability"}
        p = briefs.build_prompt([item])
        self.assertIn("Measures of Center and Variability", p)
        self.assertIn("NEVER write filler steps", p)

    def test_prompt_carries_the_evidence(self):
        item = {"id": "abc", "course": "Pop Culture", "title": "Response: Degas", "due": "2026-09-22T19:00:00",
                "hours": 2, "body": "Read and write 200-500 words.", "materials": ["Degas: A superfan"],
                "notes": "responses due Tuesdays"}
        p = briefs.build_prompt([item])
        for needle in ("id=abc", "Pop Culture", "Response: Degas", "200-500 words", "Degas: A superfan", "Tuesdays"):
            self.assertIn(needle, p)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        fd, self.store = tempfile.mkstemp(suffix=".json"); os.close(fd); os.remove(self.store)
        self._store = briefs.STORE
        briefs.STORE = self.store
        self.courses = [{"key": "if", "short": "Pop Culture", "deadlines": [
            {"title": "Response: Degas", "due": "2027-09-22T19:00:00", "body": "Read and write.",
             "priority": {"id": "abc", "hours": 2}}]}]

    def tearDown(self):
        briefs.STORE = self._store
        if os.path.exists(self.store):
            os.remove(self.store)

    def test_new_assignment_gets_a_brief_attached_and_saved(self):
        with mock.patch("briefs.ask", return_value=briefs.validate(GOOD)) as ask:
            briefs.apply(self.courses)
        self.assertEqual(self.courses[0]["deadlines"][0]["brief"]["steps"][0]["name"], "read the piece")
        self.assertIn("abc", json.load(open(self.store)))
        self.assertEqual(ask.call_count, 1)

    def test_unchanged_text_is_not_asked_again(self):
        with mock.patch("briefs.ask", return_value=briefs.validate(GOOD)):
            briefs.apply(self.courses)
        with mock.patch("briefs.ask") as ask:
            briefs.apply(self.courses)
        ask.assert_not_called()
        self.assertIn("brief", self.courses[0]["deadlines"][0])

    def test_changed_text_is_asked_again(self):
        with mock.patch("briefs.ask", return_value=briefs.validate(GOOD)):
            briefs.apply(self.courses)
        self.courses[0]["deadlines"][0]["body"] = "Now it is a podcast too."
        with mock.patch("briefs.ask", return_value=briefs.validate(GOOD)) as ask:
            briefs.apply(self.courses)
        self.assertEqual(ask.call_count, 1)

    def test_failure_leaves_no_brief(self):
        with mock.patch("briefs.ask", return_value={}):
            briefs.apply(self.courses)
        self.assertNotIn("brief", self.courses[0]["deadlines"][0])

    def test_past_deadlines_are_not_asked_about(self):
        self.courses[0]["deadlines"][0]["due"] = "2020-01-01T00:00:00"
        with mock.patch("briefs.ask", return_value={}) as ask:
            briefs.apply(self.courses)
        ask.assert_not_called()

    def test_budget_limits_one_run(self):
        many = [{"key": "c", "short": "C", "deadlines": [
            {"title": "t%d" % i, "due": "2027-10-0%dT19:00:00" % (i + 1), "priority": {"id": "id%d" % i}}
            for i in range(5)]}]
        with mock.patch("briefs.ask", return_value={}) as ask:
            briefs.apply(many, budget=2)
        self.assertEqual(len(ask.call_args[0][0]), 2)


if __name__ == "__main__":
    unittest.main()
