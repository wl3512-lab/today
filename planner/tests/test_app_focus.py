import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import state_server


class FocusPrecedenceTests(unittest.TestCase):
    """The Today tab used to be the only writer of oneThing. Study writes
    `focus` instead, and the menubar prefers it - falling back so old days and
    planner.html keep working."""

    def test_focus_wins_when_a_block_is_running(self):
        self.assertEqual(
            state_server.format_title("hand in essay", False, focus="STAT101 HW2"),
            "\U0001FAA9 STAT101 HW2")

    def test_one_thing_is_the_fallback(self):
        self.assertEqual(
            state_server.format_title("hand in essay", False),
            "\U0001FAA9 hand in essay")
        self.assertEqual(
            state_server.format_title("hand in essay", False, focus=""),
            "\U0001FAA9 hand in essay")

    def test_a_running_block_is_never_reported_as_done(self):
        # done belongs to oneThing; a live pomodoro is not done.
        self.assertEqual(
            state_server.format_title("hand in essay", True, focus="STAT101 HW2"),
            "\U0001FAA9 STAT101 HW2")

    def test_plain_heart_when_there_is_nothing_at_all(self):
        self.assertEqual(state_server.format_title("", False), "\U0001FAA9")

    def test_nudge_fires_for_a_running_block(self):
        self.assertTrue(state_server.should_notify("", False, focus="STAT101 HW2"))

    def test_nudge_still_respects_a_finished_one_thing(self):
        self.assertFalse(state_server.should_notify("hand in essay", True))
        self.assertTrue(state_server.should_notify("hand in essay", False))

    def test_nothing_to_say_means_silence(self):
        self.assertFalse(state_server.should_notify("", False))

    def test_focus_round_trips_through_save_state(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
            path = fh.name
        try:
            saved = state_server.save_state(path, {"oneThing": "x", "focus": "STAT101 HW2"})
            self.assertEqual(saved["focus"], "STAT101 HW2")
            self.assertEqual(state_server.load_state(path)["focus"], "STAT101 HW2")
        finally:
            os.unlink(path)

    def test_a_state_file_without_focus_still_loads(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"oneThing": "x"}, fh)
            path = fh.name
        try:
            self.assertEqual(state_server.load_state(path)["focus"], "")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
