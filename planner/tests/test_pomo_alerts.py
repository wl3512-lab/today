import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pomo_alerts

MIN = 60000
NOW = 1_000_000_000_000


class AlertsForTests(unittest.TestCase):
    def test_work_block_warns_then_announces_break_and_its_end(self):
        snap = {"phase": "work", "endAt": NOW + 25 * MIN, "subject": "STAT101 HW2", "nextBreakMin": 5, "nextWorkMin": 25}
        got = pomo_alerts.alerts_for(snap, NOW)
        self.assertEqual([(a - NOW) / MIN for a, _, _, _ in got], [23, 25, 29, 30])
        self.assertEqual([t for _, t, _, _ in got], ["Break in 2 minutes", "Break time", "Break ends in 1 minute", "Break's over"])
        self.assertIn("STAT101 HW2", got[0][2])
        self.assertEqual(got[1][2], "5 minutes. Step away from the screen.")
        self.assertTrue(got[3][2].startswith("25 minutes on STAT101 HW2"))

    def test_fourth_block_gets_a_long_break_that_closes_the_set(self):
        snap = {"phase": "work", "endAt": NOW + 25 * MIN, "nextBreakMin": 20, "lastBlock": True}
        got = pomo_alerts.alerts_for(snap, NOW)
        self.assertEqual([t for _, t, _, _ in got], ["Break in 2 minutes", "Long break", "Break ends in 1 minute", "Set done"])
        self.assertEqual((got[3][0] - NOW) / MIN, 45)

    def test_break_phase_only_schedules_its_own_end(self):
        snap = {"phase": "break", "endAt": NOW + 5 * MIN, "subject": "applab"}
        got = pomo_alerts.alerts_for(snap, NOW)
        self.assertEqual([((a - NOW) / MIN, t) for a, t, _, _ in got], [(4, "Break ends in 1 minute"), (5, "Break's over")])
        self.assertIn("on applab", got[1][2])

    def test_set_done_break_says_so(self):
        got = pomo_alerts.alerts_for({"phase": "break", "endAt": NOW + 20 * MIN, "setDone": True}, NOW)
        self.assertEqual(got[-1][1:3], ("Set done", "Four down. That was a whole set."))

    def test_past_alerts_are_dropped_and_idle_means_nothing(self):
        # a resumed block with 90 seconds left: the 2-minute warning is already gone
        got = pomo_alerts.alerts_for({"phase": "work", "endAt": NOW + 90 * 1000, "nextBreakMin": 5}, NOW)
        self.assertEqual([t for _, t, _, _ in got], ["Break time", "Break ends in 1 minute", "Break's over"])
        self.assertEqual(pomo_alerts.alerts_for({"phase": "idle"}, NOW), [])
        self.assertEqual(pomo_alerts.alerts_for({"phase": "work", "endAt": "nope"}, NOW), [])
        self.assertEqual(pomo_alerts.alerts_for(None, NOW), [])


class FakeTimer:
    made = []

    def __init__(self, delay, fn, args=()):
        self.delay, self.fn, self.args, self.cancelled = delay, fn, args, False
        FakeTimer.made.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        FakeTimer.made = []
        self.sent = []
        self.sched = pomo_alerts.Scheduler(notify=lambda t, b, sub, kind: self.sent.append((t, b, kind)), timer=FakeTimer, now_ms=lambda: NOW)

    def test_a_new_phase_replaces_the_pending_plan(self):
        out = self.sched.set({"phase": "work", "endAt": NOW + 25 * MIN, "nextBreakMin": 5})
        self.assertEqual(len(out["scheduled"]), 4)
        first = list(FakeTimer.made)
        self.assertEqual([t.delay for t in first], [23 * 60, 25 * 60, 29 * 60, 30 * 60])
        self.sched.set({"phase": "break", "endAt": NOW + 5 * MIN})
        self.assertTrue(all(t.cancelled for t in first))
        self.assertEqual([t for _, t in self.sched.pending()], ["Break ends in 1 minute", "Break's over"])

    def test_idle_clears_everything(self):
        self.sched.set({"phase": "work", "endAt": NOW + 25 * MIN})
        self.assertEqual(self.sched.clear(), {"scheduled": []})
        self.assertTrue(all(t.cancelled for t in FakeTimer.made))
        self.assertEqual(self.sched.pending(), [])

    def test_timer_fires_the_notifier_with_title_and_body(self):
        self.sched.set({"phase": "break", "endAt": NOW + 5 * MIN, "subject": "media"})
        for t in FakeTimer.made:
            t.fn(*t.args)
        self.assertEqual(self.sent[0], ("Break ends in 1 minute", "Back on media next.", pomo_alerts.SOFT))

    def test_real_timer_is_a_daemon_thread(self):
        real = pomo_alerts.Scheduler(notify=lambda *a: None, now_ms=lambda: NOW)
        real.set({"phase": "break", "endAt": NOW + 5 * MIN})
        self.assertTrue(all(isinstance(t, threading.Timer) and t.daemon for _, _, t in real._pending))
        real.clear()


class DeliveryKindTests(unittest.TestCase):
    """The bug this split exists for: an unregistered sender's notification is
    delivered to Notification Center and never drawn, so the two moments that
    have to interrupt cannot be a notification alone."""

    def test_phase_boundaries_are_hard_and_lead_ins_are_soft(self):
        got = pomo_alerts.alerts_for(
            {"phase": "work", "endAt": NOW + 25 * MIN, "nextBreakMin": 5}, NOW)
        self.assertEqual(
            [(t, k) for _, t, _, k in got],
            [("Break in 2 minutes", pomo_alerts.SOFT),
             ("Break time", pomo_alerts.HARD),
             ("Break ends in 1 minute", pomo_alerts.SOFT),
             ("Break's over", pomo_alerts.HARD)])

    def test_hard_alert_also_raises_a_modal_soft_one_does_not(self):
        scripts = []
        real = pomo_alerts._osa
        pomo_alerts._osa = lambda s, t: scripts.append(s)
        try:
            pomo_alerts.banner("Break time", "5 minutes.", kind=pomo_alerts.HARD)
            hard = list(scripts)
            scripts.clear()
            pomo_alerts.banner("Break in 2 minutes", "Find a stopping point.")
            soft = list(scripts)
        finally:
            pomo_alerts._osa = real
        self.assertEqual(len(hard), 2)
        self.assertTrue(hard[0].startswith("display notification"))
        self.assertTrue(hard[1].startswith("display alert"))
        self.assertIn("giving up after", hard[1])
        self.assertEqual(len(soft), 1)
        self.assertTrue(soft[0].startswith("display notification"))

    def test_every_alert_carries_a_sound(self):
        scripts = []
        real = pomo_alerts._osa
        pomo_alerts._osa = lambda s, t: scripts.append(s)
        try:
            pomo_alerts.banner("t", "m")
            pomo_alerts.banner("t", "m", kind=pomo_alerts.HARD)
        finally:
            pomo_alerts._osa = real
        self.assertIn("sound name", scripts[0])
        self.assertIn("sound name", scripts[1])


if __name__ == "__main__":
    unittest.main()
