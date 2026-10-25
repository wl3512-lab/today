import json
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calendar_feed
import gcal_sync

NOW = datetime(2026, 9, 27, 10, 0)


class FakeCalendar:
    def __init__(self):
        self.events, self.calls, self.n = {}, [], 0

    def __call__(self, args):
        self.calls.append(args[2])
        params = json.loads(args[4])
        if args[2] == "insert":
            self.n += 1
            eid = "ev%d" % self.n
            self.events[eid] = json.loads(args[6])
            return {"id": eid}
        if args[2] == "delete":
            if params["eventId"] not in self.events:
                raise RuntimeError("404 Not Found")
            del self.events[params["eventId"]]
            return {}


class Ledger:
    def __init__(self, plans):
        self.data = {"plans": plans, "calEvents": {}}

    def load(self):
        return json.loads(json.dumps(self.data))

    def save_events(self, fn):
        fn(self.data["calEvents"])


def plan(*ats, **kw):
    return dict({"sessions": [{"at": a, "minutes": 60} for a in ats],
                 "due": "2026-10-01T23:59"}, **kw)


class DiffTests(unittest.TestCase):
    def test_new_future_session_is_created_past_one_is_not(self):
        create, delete = gcal_sync.diff({"d1": plan("2026-09-26T10:00", "2026-09-28T12:00")}, {}, NOW)
        self.assertEqual([c[0] for c in create], ["d1|2026-09-28T12:00"])
        self.assertEqual(delete, [])

    def test_moved_session_deletes_old_event(self):
        create, delete = gcal_sync.diff({"d1": plan("2026-09-29T12:00")},
                                        {"d1|2026-09-28T12:00": "ev1"}, NOW)
        self.assertEqual([c[0] for c in create], ["d1|2026-09-29T12:00"])
        self.assertEqual(delete, [("d1|2026-09-28T12:00", "ev1")])

    def test_resized_session_replaces_its_event(self):
        p = {"sessions": [{"at": "2026-09-28T12:00", "minutes": 90}], "due": "2026-10-01T23:59"}
        create, delete = gcal_sync.diff({"d1": p}, {"d1|2026-09-28T12:00": "ev1"}, NOW)
        self.assertEqual([c[0] for c in create], ["d1|2026-09-28T12:00|90"])
        self.assertEqual(delete, [("d1|2026-09-28T12:00", "ev1")])
        self.assertEqual(gcal_sync.event_body("d1", create[0][2], p, None)["end"]["dateTime"],
                         "2026-09-28T13:30:00")

    def test_hour_long_sessions_keep_their_old_keys(self):
        create, delete = gcal_sync.diff({"d1": plan("2026-09-28T12:00")},
                                        {"d1|2026-09-28T12:00": "ev1"}, NOW)
        self.assertEqual((create, delete), ([], []))

    def test_quarter_hour_start_is_kept(self):
        p = {"sessions": [{"at": "2026-09-28T12:15", "minutes": 45}], "due": "2026-10-01T23:59"}
        body = gcal_sync.event_body("d1", p["sessions"][0], p, None)
        self.assertEqual((body["start"]["dateTime"], body["end"]["dateTime"]),
                         ("2026-09-28T12:15:00", "2026-09-28T13:00:00"))


class ReconcileTests(unittest.TestCase):
    def test_create_move_and_clear_keep_calendar_in_step(self):
        cal, L = FakeCalendar(), Ledger({"d1": plan("2026-09-28T12:00", title="Week 4", course="Coding")})
        run = lambda: gcal_sync.reconcile(L.load, L.save_events, cal,
                                          cache_path="/nonexistent", now=NOW)
        self.assertEqual(run(), [])
        (eid,) = L.data["calEvents"].values()
        ev = cal.events[eid]
        self.assertEqual(ev["summary"], "Study · Coding · Week 4")
        self.assertEqual(ev["start"]["dateTime"], "2026-09-28T12:00:00")
        self.assertEqual(ev["end"]["dateTime"], "2026-09-28T13:00:00")
        self.assertIn(gcal_sync.MARKER + "d1", ev["description"])

        L.data["plans"]["d1"]["sessions"][0]["at"] = "2026-09-30T15:00"
        run()
        self.assertEqual(list(L.data["calEvents"]), ["d1|2026-09-30T15:00"])
        self.assertEqual(len(cal.events), 1)

        del L.data["plans"]["d1"]
        run()
        self.assertEqual(L.data["calEvents"], {})
        self.assertEqual(cal.events, {})

    def test_event_deleted_by_hand_in_calendar_is_forgotten(self):
        cal, L = FakeCalendar(), Ledger({})
        L.data["calEvents"] = {"d1|2026-09-28T12:00": "gone"}
        self.assertEqual(gcal_sync.reconcile(L.load, L.save_events, cal, "/nonexistent"), [])
        self.assertEqual(L.data["calEvents"], {})

    def test_nothing_to_do_makes_no_calls(self):
        cal, L = FakeCalendar(), Ledger({})
        gcal_sync.reconcile(L.load, L.save_events, cal, "/nonexistent")
        self.assertEqual(cal.calls, [])


class TaskEvents(unittest.TestCase):
    def test_own_task_is_named_as_typed_with_no_due_line(self):
        ev = gcal_sync.event_body("t_abc", {"at": "2026-09-28T10:00", "minutes": 60},
                                  {"title": "laundry", "due": None}, None)
        self.assertEqual(ev["summary"], "laundry")
        self.assertFalse(ev["description"].startswith("Due"))


class FeedSkipsPlannerEvents(unittest.TestCase):
    def test_marker_event_is_not_busy(self):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
        ics = ("BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20260928T120000\n"
               "DTEND;TZID=America/New_York:20260928T130000\nSUMMARY:Study\n"
               "DESCRIPTION:Planned in Today. today-planner:d1\nUID:a\nEND:VEVENT\n"
               "BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20260928T140000\n"
               "DTEND;TZID=America/New_York:20260928T150000\nSUMMARY:Class\nUID:b\nEND:VEVENT\n")
        start = datetime(2026, 9, 27, tzinfo=tz)
        blocks = calendar_feed.expand(calendar_feed.parse_ics(ics, tz), start,
                                      datetime(2026, 10, 4, tzinfo=tz))
        self.assertEqual([b["title"] for b in blocks], ["Class"])


if __name__ == "__main__":
    unittest.main()
