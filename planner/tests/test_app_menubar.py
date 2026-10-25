"""The menubar's two readers of state.json, exercised on the real methods.

`rumps` imports cleanly without opening anything - every AppKit call in app.py
lives inside a function body, and the launch is behind an __name__ guard - so
these drive TodayApp.update_title and TodayApp.maybe_notify directly rather
than trusting that state_server's unit tests describe how app.py calls them.

TodayApp.__init__ would build a real status item, so the methods are bound to a
stand-in that supplies only what they touch: `title` and `_todays_state`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app


class _Menubar:
    """Enough of TodayApp for the two methods under test."""

    update_title = app.TodayApp.update_title
    maybe_notify = app.TodayApp.maybe_notify

    def __init__(self, state):
        self._state = state
        self.title = None

    def _todays_state(self):
        # Bypassed deliberately: the day-rollover logic has its own tests, and
        # these are about what the two methods do with a day once they have one.
        return self._state


class MenubarReadsFocusTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._real_notify = app.notify
        app.notify = lambda title, msg, subtitle="": self.sent.append((title, msg))

    def tearDown(self):
        app.notify = self._real_notify

    def test_a_running_block_owns_the_title_and_the_nudge(self):
        bar = _Menubar({"oneThing": "hand in essay", "done": False, "focus": "STAT101 HW2"})
        bar.update_title(None)
        self.assertEqual(bar.title, "\U0001FAA9 STAT101 HW2")
        bar.maybe_notify(None)
        self.assertEqual(self.sent, [("Still on it?", "STAT101 HW2")])

    def test_no_running_block_falls_back_to_one_thing(self):
        bar = _Menubar({"oneThing": "hand in essay", "done": False, "focus": ""})
        bar.update_title(None)
        self.assertEqual(bar.title, "\U0001FAA9 hand in essay")
        bar.maybe_notify(None)
        self.assertEqual(self.sent, [("Still on it?", "hand in essay")])

    def test_a_state_file_predating_focus_still_works(self):
        # planner.html posts five fields; load_state fills focus in, but be
        # explicit that a dict without the key cannot break the call sites.
        bar = _Menubar({"oneThing": "hand in essay", "done": False})
        bar.update_title(None)
        self.assertEqual(bar.title, "\U0001FAA9 hand in essay")
        bar.maybe_notify(None)
        self.assertEqual(self.sent, [("Still on it?", "hand in essay")])

    def test_nothing_running_and_nothing_typed_stays_quiet(self):
        bar = _Menubar({"oneThing": "", "done": False, "focus": ""})
        bar.update_title(None)
        self.assertEqual(bar.title, "\U0001FAA9")
        bar.maybe_notify(None)
        self.assertEqual(self.sent, [])


class RolloverClearsFocusTests(unittest.TestCase):
    """The guard that stops yesterday nagging today has to cover `focus` too.

    A block that was running when Chrome quit leaves its subject in state.json.
    Without this the menubar reads it the next morning and nudges about a block
    abandoned the day before - the exact failure the oneThing guard exists for,
    reached through the field the rebuild added.
    """

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "state.json")
        self._real_path = app.STATE_PATH
        app.STATE_PATH = self.path

    def tearDown(self):
        app.STATE_PATH = self._real_path

    def _write(self, **fields):
        import json
        with open(self.path, "w") as fh:
            json.dump(fields, fh)

    def _todays(self):
        bar = app.TodayApp.__new__(app.TodayApp)
        return app.TodayApp._todays_state(bar)

    def test_a_block_left_running_yesterday_is_not_still_running_today(self):
        self._write(oneThing="hand in essay", done=False,
                    focus="STAT101 HW2", anchorsDate="2020-1-1")
        state = self._todays()
        self.assertEqual(state["focus"], "")
        self.assertEqual(state["oneThing"], "")
        self.assertFalse(state["done"])

    def test_todays_focus_survives(self):
        import datetime
        t = datetime.date.today()
        self._write(oneThing="hand in essay", done=False, focus="STAT101 HW2",
                    anchorsDate="%d-%d-%d" % (t.year, t.month, t.day))
        self.assertEqual(self._todays()["focus"], "STAT101 HW2")


if __name__ == "__main__":
    unittest.main()
