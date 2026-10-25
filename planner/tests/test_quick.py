"""Menubar sessions: what they open, what the menubar shows, what gets logged."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kit
import ledger
import pomo_alerts
import quick

REG = {"studyPlaylist": "https://soundcloud.com/me/sets/study",
       "courses": [{"key": "coding", "short": "Coding", "name": "Intro to Programming"},
                   {"key": "writing", "name": "Writing Seminar"}, {"name": "no key"}]}


class QuickTests(unittest.TestCase):
    def test_classes_use_short_name_and_skip_keyless(self):
        self.assertEqual(quick.classes(REG), [("coding", "Coding"), ("writing", "Writing Seminar")])

    def test_study_opens_focus_then_study_playlist(self):
        cmds = quick.start_cmds("study", REG)
        self.assertEqual(cmds[0], ["shortcuts", "run", kit.FOCUS_ON])
        self.assertIn("https://soundcloud.com/me/sets/study", cmds[1])

    def test_reading_plays_spotify_default(self):
        cmds = quick.start_cmds("reading", REG)
        self.assertEqual(cmds[1], ["open", quick.READING_PLAYLIST])
        cmd = cmds[2]
        self.assertEqual(cmd[0], "/usr/bin/osascript")
        self.assertIn('play track "%s"' % quick.READING_PLAYLIST, cmd[2])

    def test_reading_override_accepts_a_spotify_link(self):
        reg = dict(REG, readingPlaylist="https://open.spotify.com/playlist/abc123?si=x")
        self.assertIn('"spotify:playlist:abc123"', quick.start_cmds("reading", reg)[2][2])

    def test_reading_ignores_a_non_spotify_override(self):
        reg = dict(REG, readingPlaylist="https://soundcloud.com/x/sets/read")
        self.assertIn(quick.READING_PLAYLIST, quick.start_cmds("reading", reg)[2][2])

    def test_only_reading_pauses_spotify_at_the_end(self):
        self.assertIn("pause", quick.stop_cmds("reading")[-1][2])
        self.assertEqual(quick.stop_cmds("study"), kit.stop_cmds())

    def test_journal_is_focus_only(self):
        self.assertEqual(quick.start_cmds("journal", REG), [["shortcuts", "run", kit.FOCUS_ON]])

    def test_countdown_rounds_up(self):
        self.assertEqual(quick.countdown_title("study", "Coding", 30), "\U0001F4DA Coding 1m")
        self.assertEqual(quick.countdown_title("reading", None, 45 * 60), "\U0001F4D6 Reading 45m")

    def test_elapsed_is_capped_at_the_block(self):
        self.assertEqual(quick.elapsed_minutes(0, 60 * 60, 25), 25)
        self.assertEqual(quick.elapsed_minutes(0, 10 * 60 + 20, 25), 10)

    def test_session_is_logged_with_kind_and_note(self):
        data = ledger.apply_op({"sessions": []},
                               quick.session_op("study", 25, "coding", "  SwiftUI practice "))
        s = data["sessions"][0]
        self.assertEqual((s["minutes"], s["courseKey"], s["kind"], s["note"]),
                         (25, "coding", "study", "SwiftUI practice"))

    def test_reading_carries_no_class_and_blank_note_is_dropped(self):
        s = ledger.apply_op({"sessions": []}, quick.session_op("reading", 40, "coding", ""))["sessions"][0]
        self.assertIsNone(s["courseKey"])
        self.assertNotIn("note", s)

    def test_planner_sessions_are_unchanged(self):
        s = ledger.apply_op({"sessions": []}, {"addSession": {"minutes": 5}})["sessions"][0]
        self.assertEqual(set(s), {"at", "minutes", "courseKey", "deadlineId", "sid"})

FOCUS = ["shortcuts", "run", kit.FOCUS_ON]


class StartAlertTests(unittest.TestCase):
    """What a start sounds like - the countdown alone is no proof, Ice hides it."""

    def test_focus_on_is_a_sound_not_a_modal(self):
        title, msg, kind = quick.start_alert("journal", None, 15, [(FOCUS, True, "")])
        self.assertEqual(kind, pomo_alerts.SOFT)
        self.assertIn("Journal", title)
        self.assertIn("15", title)

    def test_a_missing_focus_shortcut_says_how_to_make_it(self):
        res = [(FOCUS, False, "Error: The operation couldn’t be completed. Couldn’t find shortcut")]
        title, msg, kind = quick.start_alert("journal", None, 15, res)
        self.assertEqual(kind, pomo_alerts.HARD)
        self.assertIn('"%s"' % kit.FOCUS_ON, msg)
        self.assertIn('"%s"' % kit.FOCUS_OFF, msg)

    def test_any_other_focus_failure_is_shown_as_is(self):
        title, msg, kind = quick.start_alert("study", "Coding", 25, [(FOCUS, False, "timed out after 10s")])
        self.assertEqual(kind, pomo_alerts.HARD)
        self.assertIn("timed out after 10s", msg)
        self.assertIn("Coding", title)

    def test_a_playlist_failure_alone_does_not_interrupt(self):
        res = [(FOCUS, True, ""), (["open", "x"], False, "exit 1")]
        self.assertEqual(quick.start_alert("study", "Coding", 25, res)[2], pomo_alerts.SOFT)


class SavedSessionTests(unittest.TestCase):
    """A running session outlives a relaunch of the menubar app."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "session.json")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_round_trip(self):
        s = {"mode": "journal", "key": None, "short": None, "note": "",
             "started": 100.0, "ends": 1000.0, "minutes": 15}
        quick.save_session(s, self.path)
        self.assertEqual(quick.load_session(self.path), s)

    def test_saving_none_forgets_it(self):
        quick.save_session({"mode": "journal", "started": 1, "ends": 2, "minutes": 15}, self.path)
        quick.save_session(None, self.path)
        self.assertFalse(os.path.exists(self.path))
        self.assertIsNone(quick.load_session(self.path))

    def test_nothing_or_garbage_loads_as_none(self):
        self.assertIsNone(quick.load_session(self.path))
        with open(self.path, "w") as fh:
            fh.write("{not json")
        self.assertIsNone(quick.load_session(self.path))
        with open(self.path, "w") as fh:
            json.dump({"mode": "napping", "started": 1, "ends": 2, "minutes": 15}, fh)
        self.assertIsNone(quick.load_session(self.path))


if __name__ == "__main__":
    unittest.main()
