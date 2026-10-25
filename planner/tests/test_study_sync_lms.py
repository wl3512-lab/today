import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import study_sync

FEED = {"source": "canvas", "fetchedAt": "2026-10-01T12:00:00Z", "stale": True, "items": [
    {"id": "canvas:deadline:11:1", "source": "canvas", "kind": "deadline", "title": "PS 3",
     "body": "", "url": "https://canvas.example.edu/courses/11/assignments/1",
     "at": "2026-10-03T03:59:00Z", "context": "Chem", "status": "open", "meta": {"courseId": 11}},
], "errors": []}


class LmsConnectorTests(unittest.TestCase):
    def test_shipped_connectors_win(self):
        for name, script in (("brightspace", "bs"), ("canvas", "canvas"), ("campuswire", "cw")):
            self.assertEqual(study_sync.connector(name, script),
                             os.path.join(study_sync.CONNECTORS, name, script))
            self.assertTrue(os.path.exists(study_sync.connector(name, script)))

    def test_unshipped_connector_falls_back_to_a_skill(self):
        self.assertEqual(study_sync.connector("discord", "dc"), os.path.expanduser("~/.claude/skills/discord/dc"))

    def test_the_test_profile_reads_brightspace(self):
        self.assertEqual(study_sync.LMS, "brightspace")
        self.assertTrue(study_sync.BS.endswith(os.path.join("connectors", "brightspace", "bs")))

    def test_no_platform_means_no_call(self):
        with mock.patch.object(study_sync, "LMS", None), mock.patch.object(study_sync, "run") as run:
            self.assertEqual(study_sync.brightspace_items([]), {})
            run.assert_not_called()

    def test_canvas_items_are_keyed_by_course_and_name_their_login(self):
        errors = []
        with mock.patch.object(study_sync, "LMS", "canvas"), \
             mock.patch.object(study_sync, "run", return_value=(0, json.dumps(FEED), "")):
            by_course = study_sync.brightspace_items(errors)
        self.assertEqual(list(by_course), ["11"])
        self.assertEqual(errors[0]["source"], "canvas")
        self.assertIn("canvas login", errors[0]["error"])


if __name__ == "__main__":
    unittest.main()
