"""Menubar sessions as the app runs them: start, relaunch, and what she is told.

Pressing Journalling looked like it did nothing. It had started - the countdown
was in the menubar - but Ice files the Today item into its hidden section and
re-hides it 15s after she clicks, and the one thing journalling does besides
the clock (turn the Study focus on) failed because there was no Shortcut by
that name. `_run_bg` threw the failure away, so nothing said so.

Like test_app_menubar, the real methods are bound to a stand-in: TodayApp's
__init__ would build a status item.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
import kit
import pomo_alerts
import quick

FOCUS = ["shortcuts", "run", kit.FOCUS_ON]
MISSING = "Error: The operation couldn’t be completed. Couldn’t find shortcut"


class _Timer:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class _Menubar:
    start_session = app.TodayApp.start_session
    tick_session = app.TodayApp.tick_session
    end_session = app.TodayApp.end_session
    _resume_session = app.TodayApp._resume_session

    def __init__(self, focus_ok=True):
        self.session = None
        self.title = None
        self.session_timer = _Timer()
        self.ran = []
        self.focus_ok = focus_ok

    def _run_bg(self, cmds, then=None):
        # synchronous, and Focus answers the way this test says
        results = [(c, c != FOCUS or self.focus_ok, "" if c != FOCUS or self.focus_ok else MISSING)
                   for c in cmds]
        self.ran.append(cmds)
        if then:
            then(results)

    def _show_end(self, shown):
        pass

    def update_title(self, _timer):
        self.title = "heart"


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = quick.SESSION_FILE
        quick.SESSION_FILE = os.path.join(self.dir, "session.json")
        self.alerts, self.logged = [], []
        self._banner, self._apply = pomo_alerts.banner, app.apply_ledger
        pomo_alerts.banner = lambda title, msg, subtitle="", kind=pomo_alerts.SOFT: \
            self.alerts.append((title, msg, kind))
        app.apply_ledger = self.logged.append
        self._reg = quick.load_registry
        quick.load_registry = lambda path=None: {}

    def tearDown(self):
        quick.SESSION_FILE = self._saved
        pomo_alerts.banner, app.apply_ledger = self._banner, self._apply
        quick.load_registry = self._reg
        shutil.rmtree(self.dir)

    def test_journalling_starts_a_clock_and_says_so(self):
        bar = _Menubar()
        bar.start_session("journal")
        self.assertEqual(bar.title, "✏️ Journal 15m")
        self.assertEqual(bar.ran, [[FOCUS]])
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.alerts[0][2], pomo_alerts.SOFT)

    def test_a_missing_focus_shortcut_is_said_out_loud(self):
        bar = _Menubar(focus_ok=False)
        bar.start_session("journal")
        title, msg, kind = self.alerts[0]
        self.assertEqual(kind, pomo_alerts.HARD)
        self.assertIn(kit.FOCUS_ON, msg)
        self.assertTrue(bar.session_timer.running)         # the clock still runs without Focus

    def test_a_relaunch_picks_the_session_back_up(self):
        bar = _Menubar()
        bar.start_session("journal")
        again = _Menubar()                                  # the app after KeepAlive restarts it
        again._resume_session()
        self.assertEqual(again.session["mode"], "journal")
        self.assertTrue(again.session_timer.running)
        self.assertTrue(again.title.startswith("✏️ Journal"))
        self.assertEqual(again.ran, [])                     # no second Focus run, no second alert

    def test_ending_forgets_the_saved_session(self):
        bar = _Menubar()
        bar.start_session("journal")
        bar.end_session("menu item")
        again = _Menubar()
        again._resume_session()
        self.assertIsNone(again.session)

    def test_a_session_that_ran_out_while_the_app_was_down_is_logged_quietly(self):
        now = time.time()
        quick.save_session({"mode": "journal", "key": None, "short": None, "note": "",
                            "started": now - 20 * 60, "ends": now - 5 * 60, "minutes": 15})
        bar = _Menubar()
        bar._resume_session()
        self.assertIsNone(bar.session)
        self.assertEqual(self.logged, [quick.session_op("journal", 15)])
        self.assertEqual([a for a in self.alerts if a[2] == pomo_alerts.HARD], [])
        self.assertIsNone(quick.load_session())


class _Proc:
    def __init__(self, code, err=""):
        self.returncode, self.stderr = code, err


class RunCmdsTests(unittest.TestCase):
    def test_failures_are_logged_and_returned(self):
        log = []
        runner = lambda cmd, **kw: _Proc(1, MISSING) if cmd == FOCUS else _Proc(0)
        res = app.run_cmds([FOCUS, ["open", "x"]], runner=runner, log=log.append)
        self.assertEqual(res, [(FOCUS, False, MISSING), (["open", "x"], True, "")])
        self.assertEqual(len(log), 1)
        self.assertIn("Couldn’t find shortcut", log[0])


if __name__ == "__main__":
    unittest.main()
