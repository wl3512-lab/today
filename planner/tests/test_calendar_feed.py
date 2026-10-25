# tests/test_calendar_feed.py
import os
import sys
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calendar_feed as cf

NY = ZoneInfo("America/New_York")

ICS = """BEGIN:VCALENDAR
X-WR-TIMEZONE:America/New_York
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260921T143000
DTEND;TZID=America/New_York:20260921T153000
SUMMARY:Studio Lab working session
UID:a1
END:VEVENT
BEGIN:VEVENT
DTSTART:20260916T210000Z
DTEND:20260916T220000Z
RRULE:FREQ=WEEKLY;UNTIL=20261222T045959Z;BYDAY=WE
EXDATE;TZID=America/New_York:20260930T170000
SUMMARY:practice @ 404 Fitness
UID:a2
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260915
DTEND;VALUE=DATE:20260916
SUMMARY:Add/Drop deadline
UID:a3
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260920T220000
DTEND;TZID=America/New_York:20260920T230000
SUMMARY:Acme Health Client Meeting
DESCRIPTION:folded line one\\n
  continued
UID:a4
END:VEVENT
END:VCALENDAR
"""


class ParseTests(unittest.TestCase):
    def test_timed_events_parse_with_their_zone(self):
        evs = cf.parse_ics(ICS, NY)
        by = {e["uid"]: e for e in evs}
        self.assertEqual(by["a1"]["start"], datetime(2026, 9, 21, 14, 30, tzinfo=NY))
        self.assertEqual(by["a1"]["end"], datetime(2026, 9, 21, 15, 30, tzinfo=NY))
        self.assertEqual(by["a1"]["summary"], "Studio Lab working session")

    def test_utc_events_convert_to_local(self):
        evs = {e["uid"]: e for e in cf.parse_ics(ICS, NY)}
        self.assertEqual(evs["a2"]["start"].astimezone(NY).hour, 17)

    def test_all_day_events_are_marked(self):
        evs = {e["uid"]: e for e in cf.parse_ics(ICS, NY)}
        self.assertTrue(evs["a3"]["allDay"])
        self.assertFalse(evs["a1"]["allDay"])

    def test_folded_lines_do_not_break_the_next_field(self):
        evs = {e["uid"]: e for e in cf.parse_ics(ICS, NY)}
        self.assertEqual(evs["a4"]["summary"], "Acme Health Client Meeting")


class ExpandTests(unittest.TestCase):
    def setUp(self):
        self.evs = cf.parse_ics(ICS, NY)
        self.win = (datetime(2026, 9, 18, tzinfo=NY), datetime(2026, 10, 9, tzinfo=NY))

    def test_single_event_inside_window(self):
        blocks = cf.expand(self.evs, *self.win)
        titles = [b["title"] for b in blocks]
        self.assertIn("Studio Lab working session", titles)
        self.assertIn("Acme Health Client Meeting", titles)

    def test_weekly_rule_expands_and_honours_exdate(self):
        blocks = [b for b in cf.expand(self.evs, *self.win) if b["title"].startswith("practice")]
        days = sorted(b["start"][:10] for b in blocks)
        self.assertEqual(days, ["2026-09-23", "2026-10-07"])   # 09-30 is EXDATE'd

    def test_all_day_events_are_not_busy(self):
        self.assertFalse([b for b in cf.expand(self.evs, *self.win) if "Add/Drop" in b["title"]])

    def test_blocks_are_iso_with_offset(self):
        b = [b for b in cf.expand(self.evs, *self.win) if b["title"] == "Studio Lab working session"][0]
        self.assertEqual(b["start"], "2026-09-21T14:30:00-04:00")
        self.assertEqual(b["end"], "2026-09-21T15:30:00-04:00")

    def test_events_outside_window_are_dropped(self):
        blocks = cf.expand(self.evs, datetime(2026, 11, 1, tzinfo=NY), datetime(2026, 11, 8, tzinfo=NY))
        self.assertEqual([b["title"] for b in blocks], ["practice @ 404 Fitness"])


if __name__ == "__main__":
    unittest.main()


GAPS = """BEGIN:VCALENDAR
X-WR-TIMEZONE:America/New_York
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260921T143000
DTEND;TZID=America/New_York:20260921T153000
RDATE;TZID=America/New_York:20260928T143000
SUMMARY:Studio Lab working session
UID:r1
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260908T104500
DTEND;TZID=America/New_York:20260908T111500
RRULE:FREQ=WEEKLY;BYDAY=TU,FR
SUMMARY:Lab section
UID:o1
END:VEVENT
BEGIN:VEVENT
RECURRENCE-ID;TZID=America/New_York:20260929T104500
DTSTART;TZID=America/New_York:20260930T090000
DTEND;TZID=America/New_York:20260930T093000
SUMMARY:Lab section
UID:o1
END:VEVENT
BEGIN:VEVENT
RECURRENCE-ID;TZID=America/New_York:20261002T104500
DTSTART;TZID=America/New_York:20261002T104500
DTEND;TZID=America/New_York:20261002T111500
STATUS:CANCELLED
SUMMARY:Lab section
UID:o1
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260929T120000
DTEND;TZID=America/New_York:20260929T130000
STATUS:CANCELLED
SUMMARY:called off
UID:c1
END:VEVENT
BEGIN:VEVENT
DTSTART:20260916T210000Z
DTEND:20260916T220000Z
RRULE:FREQ=WEEKLY;BYDAY=WE
SUMMARY:practice
UID:u1
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261012
DTEND;VALUE=DATE:20261013
SUMMARY:Fall Break - no State U classes
UID:d1
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20250930
DTEND;VALUE=DATE:20251001
RRULE:FREQ=YEARLY
SUMMARY:Mom birthday
UID:y1
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260915T090000
DTEND;TZID=America/New_York:20260915T100000
RRULE:FREQ=MONTHLY
SUMMARY:rent check
UID:m1
END:VEVENT
END:VCALENDAR
"""


class GapTests(unittest.TestCase):
    """Things Google writes that the first parser dropped or doubled."""

    def setUp(self):
        self.evs = cf.parse_ics(GAPS, NY)
        self.win = (datetime(2026, 9, 28, tzinfo=NY), datetime(2026, 10, 19, tzinfo=NY))
        self.blocks = cf.expand(self.evs, *self.win)

    def at(self, title):
        return [b["start"][:16] for b in self.blocks if b["title"] == title]

    def test_rdate_extra_dates_show(self):
        self.assertIn("2026-09-28T14:30", self.at("Studio Lab working session"))

    def test_moved_instance_shows_once_at_its_new_time(self):
        got = self.at("Lab section")
        self.assertIn("2026-09-30T09:00", got)
        self.assertNotIn("2026-09-29T10:45", got)

    def test_cancelled_instance_and_event_are_dropped(self):
        self.assertNotIn("2026-10-02T10:45", self.at("Lab section"))
        self.assertIn("2026-10-06T10:45", self.at("Lab section"))       # the series goes on
        self.assertEqual(self.at("called off"), [])

    def test_utc_weekly_keeps_local_time_across_dst(self):
        # 17:00 in September (EDT) stays 17:00 after the clocks change on Nov 1
        blocks = cf.expand(self.evs, datetime(2026, 11, 2, tzinfo=NY), datetime(2026, 11, 9, tzinfo=NY))
        self.assertEqual([b["start"][:16] for b in blocks if b["title"] == "practice"], ["2026-11-04T17:00"])

    def test_monthly_repeats(self):
        self.assertIn("2026-10-15T09:00", self.at("rent check"))

    def test_all_day_events_come_back_separately(self):
        days = cf.expand_all_day(self.evs, *self.win)
        self.assertIn({"date": "2026-10-12", "days": 1, "title": "Fall Break - no State U classes"}, days)
        self.assertIn({"date": "2026-09-30", "days": 1, "title": "Mom birthday"}, days)
        self.assertFalse([b for b in self.blocks if "Fall Break" in b["title"]])


class WindowTests(unittest.TestCase):
    def test_window_starts_on_monday_so_the_whole_week_shows(self):
        start = cf.week_start(datetime(2026, 10, 1, 15, 0, tzinfo=NY))   # a Thursday
        self.assertEqual(start, datetime(2026, 9, 28, tzinfo=NY))
