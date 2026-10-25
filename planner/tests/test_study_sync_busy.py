import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import study_sync


class BusyBlocksTests(unittest.TestCase):
    def setUp(self):
        fd, self.cache = tempfile.mkstemp(suffix=".json"); os.close(fd)
        self._cache = study_sync.CACHE
        study_sync.CACHE = self.cache

    def tearDown(self):
        study_sync.CACHE = self._cache
        os.remove(self.cache)

    def test_fetch_success_writes_blocks(self):
        blocks = [{"start": "2026-09-21T14:30:00-04:00", "end": "2026-09-21T15:30:00-04:00", "title": "x"}]
        days = [{"date": "2026-10-12", "days": 1, "title": "Fall Break"}]
        with mock.patch("study_sync.calendar_feed.fetch_calendar", return_value=(blocks, days)):
            out, all_day, errors = study_sync.busy_blocks({"calendar": {"ics": "https://example/basic.ics"}})
        self.assertEqual(out, blocks)
        self.assertEqual(all_day, days)
        self.assertEqual(errors, [])

    def test_several_calendars_are_merged_in_time_order(self):
        a = [{"start": "2026-09-29T10:00:00-04:00", "end": "x", "title": "later"}]
        b = [{"start": "2026-09-28T10:00:00-04:00", "end": "x", "title": "sooner"}]
        with mock.patch("study_sync.calendar_feed.fetch_calendar", side_effect=[(a, []), (b, [])]):
            out, _days, errors = study_sync.busy_blocks({"calendar": {"ics": ["https://a/basic.ics", "https://b/basic.ics"]}})
        self.assertEqual([x["title"] for x in out], ["sooner", "later"])
        self.assertEqual(errors, [])

    def test_fetch_failure_keeps_previous_blocks_and_records_error(self):
        prev = [{"start": "2026-09-21T14:30:00-04:00", "end": "2026-09-21T15:30:00-04:00", "title": "old"}]
        with open(self.cache, "w") as f:
            json.dump({"busy": prev}, f)
        with mock.patch("study_sync.calendar_feed.fetch_calendar", side_effect=OSError("boom")):
            out, _days, errors = study_sync.busy_blocks({"calendar": {"ics": "https://example/basic.ics"}})
        self.assertEqual(out, prev)
        self.assertEqual(errors[0]["source"], "calendar")

    def test_no_feed_configured_is_empty_and_quiet(self):
        self.assertEqual(study_sync.busy_blocks({}), ([], [], []))


if __name__ == "__main__":
    unittest.main()
