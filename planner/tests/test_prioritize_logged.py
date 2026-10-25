import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger
import prioritize


_NOW = datetime.now(timezone.utc).replace(microsecond=0)


def feed_with(hours_title, due_days=10):
    due = (_NOW + timedelta(days=due_days)).isoformat().replace("+00:00", "Z")
    return {"courses": [{"key": "coding", "short": "Coding",
                         "deadlines": [{"title": hours_title, "due": due, "url": ""}]}]}


class BandForTests(unittest.TestCase):
    def test_table(self):
        cases = [
            ((7.0, 0, [], "Homework"), "high"),
            ((2.5, 0, [], "Homework"), "medium"),
            ((1.0, 0, [], "Homework"), "low"),
            ((1.0, 50, [], "Homework"), "high"),
            ((1.0, 0, ["gate"], "Homework"), "medium"),
            ((7.0, 0, [], "Optional reading"), "low"),
        ]
        for args, want in cases:
            self.assertEqual(prioritize.band_for(*args), want, args)


class LoggedHoursTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.path)  # must not exist, so the "no ledger" path is exercised

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def deadline(self, feed):
        return feed["courses"][0]["deadlines"][0]

    def test_no_ledger_means_logged_zero_and_band_unchanged(self):
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        self.assertEqual(p["logged"], 0)
        self.assertEqual(p["remaining"], p["hours"])
        self.assertEqual(p["band"], "high")

    def test_logged_hours_lower_remaining_and_band(self):
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        self.assertEqual(p["band"], "high")
        did = p["id"]
        hours_before = p["hours"]
        ledger.save(self.path, {"sessions": [
            {"at": "x", "minutes": int((p["hours"] - 1.0) * 60), "courseKey": "coding", "deadlineId": did}],
            "steps": {}})
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        self.assertAlmostEqual(p["remaining"], 1.0, places=1)
        self.assertEqual(p["band"], "low")
        self.assertEqual(p["hours"], hours_before)

    def test_partial_logging_does_not_over_demote(self):
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        self.assertEqual(p["hours"], 14.0)
        self.assertEqual(p["stakes"], 50)
        did = p["id"]
        ledger.save(self.path, {"sessions": [
            {"at": "x", "minutes": int(9.0 * 60), "courseKey": "coding", "deadlineId": did}],
            "steps": {}})
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        self.assertAlmostEqual(p["remaining"], 5.0, places=1)
        self.assertEqual(p["band"], "medium")

    def test_session_on_other_deadline_does_not_count(self):
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        ledger.save(self.path, {"sessions": [
            {"at": "x", "minutes": 120, "courseKey": "coding", "deadlineId": "some-other-id"}],
            "steps": {}})
        feed = prioritize.apply(feed_with("Final project"), ai=False, ledger_path=self.path)
        p = self.deadline(feed)["priority"]
        self.assertEqual(p["logged"], 0)

    def test_fully_logged_gate_is_low_regardless_of_flags(self):
        feed = {"courses": [{"key": "x", "deadlines": [{"title": "Part 1", "priority": {
            "id": "d9", "hours": 2.0, "stakes": 0, "flags": ["gate"], "band": "medium"}}]}]}
        ledger.save(self.path, {"sessions": [
            {"at": "x", "minutes": 180, "courseKey": "x", "deadlineId": "d9"}], "steps": {}})
        prioritize.subtract_logged(feed, self.path)
        p = feed["courses"][0]["deadlines"][0]["priority"]
        self.assertEqual(p["remaining"], 0.0)
        self.assertEqual(p["band"], "low")

    def test_remaining_clamps_at_zero(self):
        feed = prioritize.apply(feed_with("Homework 1"), ai=False, ledger_path=self.path)
        did = self.deadline(feed)["priority"]["id"]
        ledger.save(self.path, {"sessions": [{"at": "x", "minutes": 6000, "courseKey": "coding", "deadlineId": did}], "steps": {}})
        feed = prioritize.apply(feed_with("Homework 1"), ai=False, ledger_path=self.path)
        self.assertEqual(self.deadline(feed)["priority"]["remaining"], 0)

    def test_focus_row_carries_logged(self):
        feed = prioritize.apply(feed_with("Final project", due_days=2), ai=False, ledger_path=self.path)
        self.assertIn("logged", feed["focus"][0])
        self.assertIn("id", feed["focus"][0])


if __name__ == "__main__":
    unittest.main()
