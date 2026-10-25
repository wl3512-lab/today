import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import study_sync

REPO = "applab-class/content-2026"
README = "| 04.  | 2026-09-25 |\n| 05.  | 2026-10-02 |\n| 06.  | 2026-10-09 |\n"
COURSE = {
    "key": "coding",
    "meets": {"start": "09:00"},
    "sources": [{"kind": "github-weekly", "url": "https://github.com/" + REPO}],
}


def run_weekly(files):
    """weekly_homework over a fake repo: `files` maps weeks/... paths to their markdown."""
    def fetch(url, errors, label):
        if url.endswith("/README.md"):
            return README
        return files.get(url.split("/HEAD/", 1)[1], "")

    tree = {"tree": [{"type": "blob", "path": p} for p in sorted(files)]}
    errors = []
    with mock.patch("study_sync.fetch_text", side_effect=fetch), \
         mock.patch("study_sync.gh_get", return_value=tree), \
         mock.patch("study_sync.now_utc",
                    return_value=datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)):
        return study_sync.weekly_homework(COURSE, errors, {}), errors


class WeeklyHomeworkTests(unittest.TestCase):
    def test_week_with_two_files_uses_the_one_that_holds_the_homework(self):
        # The coding class's week 4 has 04_DataModel.md (notes only) and 04_swiftui.md
        # (the lesson, ending in "## Homework Week04"). GitHub lists DataModel
        # first, and the homework went missing from the planner.
        out, errors = run_weekly({
            "weeks/04_DataModel.md": "# 04_DataModel\n\nNotes on @Observable.\n",
            "weeks/04_swiftui.md": "# Week 04 Swift UI 2, Audio\n\n## Lab\n\nTestFlight.\n\n"
                                   "## Homework Week04\n\nCreate a SwiftUI app with audio.\n",
        })
        week4 = [x for x in out if x["title"].startswith("Week 04")]
        self.assertEqual(len(week4), 1, out)
        self.assertEqual(week4[0]["title"], "Week 04 homework: Swift UI 2, Audio")
        self.assertIn("weeks/04_swiftui.md#homework-week04", week4[0]["url"])
        self.assertIn("SwiftUI app with audio", week4[0]["body"])
        self.assertEqual(week4[0]["due"][:16], "2026-10-02T13:00")
        self.assertEqual(errors, [])

    def test_week_with_one_file_still_works(self):
        out, _ = run_weekly({
            "weeks/05_data.md": "# Week 05 Local Data 1\n\n## Homework Week05\n\nSave a list.\n",
        })
        self.assertEqual([x["title"] for x in out], ["Week 05 homework: Local Data 1"])


if __name__ == "__main__":
    unittest.main()
