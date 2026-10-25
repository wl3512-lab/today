"""The Canvas connector turns made-up API answers into the same items bs gives."""
import importlib.machinery
import importlib.util
import os
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_loader = importlib.machinery.SourceFileLoader("canvas_cli", os.path.join(HERE, "..", "canvas", "canvas"))
_spec = importlib.util.spec_from_loader("canvas_cli", _loader)
canvas = importlib.util.module_from_spec(_spec)
_loader.exec_module(canvas)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

API = {
    "/api/v1/courses": [
        {"id": 11, "name": "Chemistry 101", "html_url": "https://canvas.example.edu/courses/11",
         "enrollments": [{"type": "student", "computed_current_score": 88.5}]},
        {"id": 12, "name": "Writing Seminar", "enrollments": []},
        {"id": None, "name": "broken"},
    ],
    "/api/v1/courses/11/assignments": [
        {"id": 1, "name": "Problem Set 3", "due_at": "2026-10-03T03:59:00Z",
         "description": "<p>Show <b>all</b> work.</p>", "html_url": "https://canvas.example.edu/courses/11/assignments/1",
         "points_possible": 20, "submission_types": ["online_upload"],
         "submission": {"workflow_state": "unsubmitted"}},
        {"id": 2, "name": "Lab 1", "due_at": "2026-09-20T03:59:00Z", "points_possible": 10,
         "submission_types": ["online_upload"],
         "submission": {"workflow_state": "graded", "score": 9, "graded_at": "2026-09-25T15:00:00Z"}},
        {"id": 3, "name": "Quiz 2", "due_at": "2026-09-28T03:59:00Z", "points_possible": 5,
         "is_quiz_assignment": True, "submission": {"workflow_state": "unsubmitted"}},
        {"id": 4, "name": "Optional reading", "due_at": None, "points_possible": 0},
    ],
    "/api/v1/courses/11/modules": [
        {"name": "Week 1", "items": [{"id": 70, "title": "Slides 1", "type": "File",
                                      "html_url": "https://canvas.example.edu/courses/11/modules/items/70"},
                                     {"id": 71, "title": "Week 1", "type": "SubHeader"}]},
    ],
    "/api/v1/courses/12/assignments": RuntimeError("403 Forbidden"),
    "/api/v1/courses/12/modules": RuntimeError("403 Forbidden"),
    "/api/v1/announcements": [
        {"id": 900, "title": "Room change", "message": "<p>We meet in 204 today.</p>",
         "posted_at": "2026-09-30T14:00:00Z", "context_code": "course_12",
         "html_url": "https://canvas.example.edu/courses/12/discussion_topics/900"},
    ],
}


def fake_get(path, params=None):
    ans = API[path]
    if isinstance(ans, Exception):
        raise ans
    return ans


class CanvasFeedTest(unittest.TestCase):
    def setUp(self):
        self.feed = canvas.build_feed(fake_get, now=NOW)
        self.by_id = {i["id"]: i for i in self.feed["items"]}

    def test_envelope(self):
        self.assertEqual(self.feed["source"], "canvas")
        self.assertFalse(self.feed["stale"])
        self.assertEqual(self.feed["fetchedAt"], "2026-10-01T12:00:00Z")

    def test_deadline_matches_the_item_contract(self):
        d = self.by_id["canvas:deadline:11:1"]
        self.assertEqual(d["kind"], "deadline")
        self.assertEqual(d["at"], "2026-10-03T03:59:00Z")
        self.assertEqual(d["status"], "open")
        self.assertEqual(d["body"], "Show all work.")
        self.assertEqual(d["context"], "Chemistry 101")
        self.assertEqual(d["meta"]["courseId"], 11)   # study_sync keys courses by this

    def test_submitted_is_done_and_missed_is_overdue(self):
        self.assertEqual(self.by_id["canvas:deadline:11:2"]["status"], "done")
        self.assertEqual(self.by_id["canvas:deadline:11:3"]["status"], "overdue")
        self.assertEqual(self.by_id["canvas:deadline:11:3"]["meta"]["type"], "quiz")

    def test_undated_assignments_are_not_deadlines(self):
        self.assertNotIn("canvas:deadline:11:4", self.by_id)

    def test_grades_carry_points_for_grades_py(self):
        g = self.by_id["canvas:grade:11:2"]
        self.assertEqual((g["meta"]["points"], g["meta"]["outOf"], g["meta"]["gradeItem"]), (9, 10, "Lab 1"))
        total = self.by_id["canvas:grade:11:total"]
        self.assertEqual(total["meta"]["points"], 88.5)

    def test_modules_become_materials_without_subheaders(self):
        self.assertIn("canvas:material:11:70", self.by_id)
        self.assertEqual(self.by_id["canvas:material:11:70"]["meta"]["module"], "Week 1")
        self.assertNotIn("canvas:material:11:71", self.by_id)

    def test_a_locked_course_is_an_error_not_a_crash(self):
        self.assertTrue(any(e["context"] == "Writing Seminar" for e in self.feed["errors"]))
        msg = self.by_id["canvas:message:12:900"]
        self.assertEqual((msg["kind"], msg["body"], msg["meta"]["courseId"]),
                         ("message", "We meet in 204 today.", 12))

    def test_auth_errors_are_not_swallowed(self):
        def deny(path, params=None):
            raise canvas.AuthError("token rejected")
        with self.assertRaises(canvas.AuthError):
            canvas.build_feed(deny, now=NOW)

    def test_next_page_link(self):
        link = '<https://x.edu/api/v1/courses?page=2>; rel="next", <https://x.edu/api/v1/courses?page=5>; rel="last"'
        self.assertEqual(canvas._next_link(link), "https://x.edu/api/v1/courses?page=2")
        self.assertIsNone(canvas._next_link('<https://x.edu/a?page=5>; rel="last"'))


if __name__ == "__main__":
    unittest.main()
