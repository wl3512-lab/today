# calendar_feed.py
"""Google Calendar's secret iCal feed -> busy blocks for the session planner.

Only what a personal calendar actually uses: timed events, daily/weekly
repeats with BYDAY/INTERVAL/UNTIL/COUNT, plain monthly/yearly repeats, EXDATE,
RDATE (the extra dates Google adds to a series), moved or cancelled instances
(RECURRENCE-ID), and cancelled events. All-day events are kept out of the busy
blocks - a deadline on the calendar is not an hour she is unavailable - and
come back separately from expand_all_day for the week view to show.
Rules stranger than that (BYSETPOS, "second Tuesday") fall back to the single
DTSTART occurrence, which is wrong quietly rather than wrong loudly.
"""
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


PLANNER_MARKER = "today-planner:"


def _unfold(text):
    # RFC 5545: a line starting with a space or tab continues the previous one.
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def _parse_dt(value, params, tz):
    """A datetime (aware) or a date. `params` is the property parameter dict."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)", value)
    if not m:
        return None
    y, mo, d, h, mi, s, z = m.groups()
    naive = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    if z:
        return naive.replace(tzinfo=timezone.utc)
    zone = tz
    if params.get("TZID"):
        try:
            zone = ZoneInfo(params["TZID"])
        except Exception:
            zone = tz
    return naive.replace(tzinfo=zone)


def _prop(line):
    """'DTSTART;TZID=X:2026...' -> ('DTSTART', {'TZID': 'X'}, '2026...')"""
    head, _, value = line.partition(":")
    name, *raw_params = head.split(";")
    params = {}
    for p in raw_params:
        k, _, v = p.partition("=")
        params[k.upper()] = v
    return name.upper(), params, value


def parse_ics(text, tz):
    """Events as dicts: uid, summary, start, end, allDay, rrule (dict|None), exdates (set of dates)."""
    events, cur = [], None
    for line in _unfold(text).split("\n"):
        line = line.strip()
        if line == "BEGIN:VEVENT":
            cur = {"uid": "", "summary": "", "start": None, "end": None,
                   "allDay": False, "rrule": None, "exdates": set(), "desc": "",
                   "rdates": [], "recurrenceId": None, "cancelled": False}
            continue
        if line == "END:VEVENT":
            if cur and cur["start"] is not None:
                if cur["end"] is None:
                    cur["end"] = cur["start"] + (timedelta(days=1) if cur["allDay"] else timedelta(hours=1))
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        name, params, value = _prop(line)
        if name == "DTSTART":
            v = _parse_dt(value, params, tz)
            cur["start"] = v
            cur["allDay"] = isinstance(v, date) and not isinstance(v, datetime)
        elif name == "DTEND":
            cur["end"] = _parse_dt(value, params, tz)
        elif name == "SUMMARY":
            cur["summary"] = value.replace("\\,", ",").replace("\\;", ";").strip()
        elif name == "DESCRIPTION":
            cur["desc"] = value
        elif name == "UID":
            cur["uid"] = value
        elif name == "RRULE":
            cur["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
        elif name == "RDATE" and params.get("VALUE") != "PERIOD":
            for part in value.split(","):
                v = _parse_dt(part, params, tz)
                if v is not None:
                    cur["rdates"].append(v)
        elif name == "RECURRENCE-ID":
            cur["recurrenceId"] = _parse_dt(value, params, tz)
        elif name == "STATUS":
            cur["cancelled"] = value.strip().upper() == "CANCELLED"
        elif name == "EXDATE":
            for part in value.split(","):
                v = _parse_dt(part, params, tz)
                if v is not None:
                    cur["exdates"].add(v.date() if isinstance(v, datetime) else v)
    return events


def _occurrences(ev, win_start, win_end):
    """Start datetimes of one event inside the window (aware, in the event's zone)."""
    start = ev["start"]
    rule = ev["rrule"]
    extra = [r for r in ev.get("rdates") or [] if isinstance(r, datetime) and win_start <= r < win_end]
    if not rule:
        base = [start] if win_start <= start < win_end or start <= win_start < ev["end"] else []
        return sorted(set(base + extra))
    return sorted(set(_ruled(ev, start, rule, win_start, win_end) + extra))


def _ruled(ev, start, rule, win_start, win_end):
    freq = rule.get("FREQ", "").upper()
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    until = rule.get("UNTIL")
    until_dt = None
    if until:
        u = _parse_dt(until, {}, start.tzinfo)
        until_dt = u if isinstance(u, datetime) else datetime.combine(u, datetime.max.time(), tzinfo=start.tzinfo)
    count = int(rule["COUNT"]) if rule.get("COUNT") else None
    out, n = [], 0
    if freq == "WEEKLY":
        days = [WEEKDAYS[d] for d in rule.get("BYDAY", "").split(",") if d in WEEKDAYS] or [start.weekday()]
        week0 = start - timedelta(days=start.weekday())
        cursor = week0
        while cursor < win_end + timedelta(days=7):
            for wd in sorted(days):
                occ = cursor + timedelta(days=wd)
                occ = occ.replace(hour=start.hour, minute=start.minute, second=start.second)
                if occ < start:
                    continue
                if until_dt and occ > until_dt:
                    return out
                n += 1
                if count and n > count:
                    return out
                if win_start <= occ < win_end:
                    out.append(occ)
            cursor += timedelta(weeks=interval)
        return out
    if freq == "DAILY":
        occ = start
        while occ < win_end:
            if until_dt and occ > until_dt:
                break
            n += 1
            if count and n > count:
                break
            if occ >= win_start:
                out.append(occ)
            occ += timedelta(days=interval)
        return out
    plain = not any(rule.get(k) for k in ("BYDAY", "BYSETPOS", "BYMONTHDAY", "BYMONTH", "BYWEEKNO", "BYYEARDAY"))
    if freq in ("MONTHLY", "YEARLY") and plain:
        step = interval if freq == "MONTHLY" else 12 * interval
        k = 0
        while True:
            months = start.month - 1 + k * step
            y, m = start.year + months // 12, months % 12 + 1
            k += 1
            try:
                occ = start.replace(year=y, month=m)
            except ValueError:                 # the 31st in a 30-day month: skipped, as RFC 5545 says
                if k > 1200:
                    break
                continue
            if occ >= win_end:
                break
            if until_dt and occ > until_dt:
                break
            n += 1
            if count and n > count:
                break
            if occ >= win_start:
                out.append(occ)
        return out
    # anything stranger: only the first occurrence, honestly
    return [start] if win_start <= start < win_end else []


def _key(v):
    """An instant to match a RECURRENCE-ID against an occurrence."""
    return v.astimezone(timezone.utc) if isinstance(v, datetime) else v


def _series(events):
    """Masters only (with the instances moved or cancelled out of them), plus
    the moved instances as their own one-off events."""
    replaced = {}
    for ev in events:
        if ev["recurrenceId"] is not None:
            replaced.setdefault(ev["uid"], set()).add(_key(ev["recurrenceId"]))
    out = []
    for ev in events:
        if ev["cancelled"]:
            continue                            # a cancelled instance still hid its slot above
        if ev["recurrenceId"] is not None:
            out.append(dict(ev, rrule=None, rdates=[]))
        else:
            out.append(dict(ev, replaced=replaced.get(ev["uid"], set())))
    return out


def _local(ev, tz):
    """A repeat anchored in UTC (Google writes some that way) would slide an
    hour at each DST change; repeat it in the calendar's zone instead."""
    st = ev["start"]
    if ev["rrule"] and isinstance(st, datetime) and st.utcoffset() == timedelta(0) and tz is not None:
        end = ev["end"]
        return dict(ev, start=st.astimezone(tz), end=end.astimezone(tz) if isinstance(end, datetime) else end)
    return ev


def expand(events, win_start, win_end):
    """Busy blocks inside [win_start, win_end): [{start, end, title}] with ISO offsets, sorted."""
    blocks = []
    for ev in _series(events):
        if ev["allDay"] or not isinstance(ev["start"], datetime):
            continue
        # sessions the planner wrote itself (gcal_sync) - it draws those already
        if PLANNER_MARKER in ev.get("desc", ""):
            continue
        ev = _local(ev, win_start.tzinfo)
        length = ev["end"] - ev["start"] if isinstance(ev["end"], datetime) else timedelta(hours=1)
        for occ in _occurrences(ev, win_start.astimezone(ev["start"].tzinfo), win_end.astimezone(ev["start"].tzinfo)):
            if occ.astimezone(win_start.tzinfo).date() in ev["exdates"] or occ.date() in ev["exdates"]:
                continue
            if _key(occ) in ev.get("replaced", ()):
                continue
            s = occ.astimezone(win_start.tzinfo)
            blocks.append({"start": s.isoformat(), "end": (s + length).isoformat(),
                           "title": ev["summary"]})
    blocks.sort(key=lambda b: b["start"])
    return blocks


def expand_all_day(events, win_start, win_end):
    """All-day events inside the window: [{date, days, title}], sorted.
    Repeats are expanded on midnight in the window's zone, then read back as dates."""
    tz = win_start.tzinfo
    out = []
    for ev in _series(events):
        if not ev["allDay"]:
            continue
        d0 = ev["start"]
        d1 = ev["end"] if isinstance(ev["end"], date) else d0 + timedelta(days=1)
        days = max(1, (d1 - d0).days)
        as_dt = dict(ev, start=datetime.combine(d0, datetime.min.time(), tzinfo=tz),
                     end=datetime.combine(d0, datetime.min.time(), tzinfo=tz) + timedelta(days=days),
                     rdates=[datetime.combine(r, datetime.min.time(), tzinfo=tz)
                             for r in ev.get("rdates") or [] if not isinstance(r, datetime)])
        for occ in _occurrences(as_dt, win_start, win_end):
            day = occ.date()
            if day in ev["exdates"] or day in ev.get("replaced", ()):
                continue
            out.append({"date": day.isoformat(), "days": days, "title": ev["summary"]})
    out.sort(key=lambda a: (a["date"], a["title"]))
    return out


def week_start(now):
    """Midnight on the Monday of now's week, so the week view has every day."""
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def fetch_text(url, timeout=30):
    """curl, not urllib: the rest of the sync fetches that way, and this
    python.org build has no certificate bundle of its own. Raises on failure."""
    p = subprocess.run(["curl", "-sSL", "-m", str(timeout), url],
                       capture_output=True, text=True, timeout=timeout + 10)
    if p.returncode != 0 or not p.stdout.strip():
        err = (p.stderr or "").strip().splitlines()
        raise RuntimeError((err[-1] if err else "empty feed")[:160])
    return p.stdout


def feed_zone(text, tz_name="America/New_York"):
    tz = ZoneInfo(tz_name)
    m = re.search(r"X-WR-TIMEZONE:(\S+)", text)
    if m:
        try:
            tz = ZoneInfo(m.group(1).strip())
        except Exception:
            pass
    return tz


def fetch_calendar(url, days=35, tz_name="America/New_York", timeout=30):
    """(busy blocks, all-day events) from the Monday of this week for `days` days."""
    text = fetch_text(url, timeout)
    tz = feed_zone(text, tz_name)
    start = week_start(datetime.now(tz))
    events = parse_ics(text, tz)
    end = start + timedelta(days=days)
    return expand(events, start, end), expand_all_day(events, start, end)


def fetch_busy(url, days=35, tz_name="America/New_York", timeout=30):
    return fetch_calendar(url, days, tz_name, timeout)[0]
