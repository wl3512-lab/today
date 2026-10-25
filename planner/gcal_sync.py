"""Planned study sessions, mirrored into her Google Calendar.

The ledger's `plans` stay the truth; this only makes the calendar agree with
them. Each session is keyed "<deadlineId>|<at>" and the event it made is kept
in ledger["calEvents"], so moving a block on the week (a new `at`) deletes
the old event and creates the new one, and removing a block deletes it.

Runs off the request thread: the page should never wait on Google. Events
carry MARKER in their description so calendar_feed can leave them out of
`busy` - otherwise every planned block would come back as a second block.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from today_profile import PROFILE

MARKER = "today-planner:"
TZ = PROFILE["timezone"]
STUDY_CACHE = os.path.expanduser("~/.study-cache.json")

# npm's global bin is not on launchd's PATH; look there by hand.
GWS = shutil.which("gws") or next(
    (p for p in (os.path.expanduser("~/.npm-global/bin/gws"), "/usr/local/bin/gws",
                 "/opt/homebrew/bin/gws") if os.path.exists(p)), "")


def gws(args, timeout=45):
    p = subprocess.run([GWS] + args, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        lines = (p.stderr or p.stdout or "").strip().splitlines()
        raise RuntimeError((lines[-1] if lines else "gws failed")[:200])
    out = p.stdout.strip()
    return json.loads(out) if out else {}


def labels(cache_path=STUDY_CACHE):
    """deadlineId -> (course short name, title), from the study cache."""
    try:
        with open(cache_path) as fh:
            cache = json.load(fh)
    except (IOError, ValueError):
        return {}
    out = {}
    for c in cache.get("courses", []):
        for d in c.get("deadlines", []) or []:
            did = (d.get("priority") or {}).get("id")
            if did:
                out[did] = (c.get("short") or c.get("name") or "", d.get("title") or "")
    return out


def _local_due(due):
    try:
        d = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
    except ValueError:
        return str(due)[:16].replace("T", " ")
    if d.tzinfo:
        d = d.astimezone(ZoneInfo(TZ))
    return d.strftime("%a %b %-d, %-I:%M%p").replace("AM", "am").replace("PM", "pm")


def event_body(did, session, plan, label):
    course, title = label or ("", "")
    course = plan.get("course") or course
    title = plan.get("title") or title or "study"
    start = datetime.strptime(session["at"][:16], "%Y-%m-%dT%H:%M")
    end = start + timedelta(minutes=int(session.get("minutes") or 60))
    due = plan.get("due")
    return {
        # her own tasks (ids "t_...") are named as she typed them
        "summary": title if did.startswith("t_") else
                   "Study · " + (course + " · " if course else "") + title,
        "description": ("Due " + _local_due(due) + "\n" if due else "")
                       + "Planned in Today. " + MARKER + did,
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": TZ},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": TZ},
        "colorId": "10",
    }


def diff(plans, cal_events, now=None):
    """(to_create [(key, did, session, plan)], to_delete [(key, eventId)]).

    Past sessions that never got an event are not backfilled."""
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%dT%H:%M")
    wanted = {}
    for did, plan in (plans or {}).items():
        for s in (plan or {}).get("sessions") or []:
            at = str(s.get("at") or "")[:16]
            if at:
                # Length is part of the key only when it is not the default
                # hour, so a block resized on the week replaces its event
                # while every existing hour-long event keeps its key.
                mins = int(s.get("minutes") or 60)
                key = did + "|" + at + ("" if mins == 60 else "|%d" % mins)
                wanted[key] = (did, dict(s, at=at), plan)
    create = [(k,) + v for k, v in wanted.items()
              if k not in cal_events and v[1]["at"] >= today]
    delete = [(k, e) for k, e in cal_events.items() if k not in wanted]
    return create, delete


def reconcile(load, save_events, run=gws, cache_path=STUDY_CACHE, now=None):
    """One pass. `load()` returns the ledger; `save_events(fn)` applies fn to
    the ledger's calEvents under the ledger lock. Returns error strings."""
    data = load()
    create, delete = diff(data.get("plans"), data.get("calEvents") or {}, now)
    if not (create or delete):
        return []
    names, errors, made, gone = labels(cache_path), [], {}, []
    for key, event_id in delete:
        try:
            run(["calendar", "events", "delete", "--params",
                 json.dumps({"calendarId": "primary", "eventId": event_id})])
            gone.append(key)
        except Exception as exc:
            msg = str(exc)
            if "404" in msg or "410" in msg or "deleted" in msg.lower():
                gone.append(key)          # already gone in the calendar
            else:
                errors.append("delete %s: %s" % (key, msg))
    for key, did, session, plan in create:
        try:
            ev = run(["calendar", "events", "insert", "--params",
                      json.dumps({"calendarId": "primary"}),
                      "--json", json.dumps(event_body(did, session, plan, names.get(did)))])
            if ev.get("id"):
                made[key] = ev["id"]
        except Exception as exc:
            errors.append("create %s: %s" % (key, exc))

    def apply(events):
        for k in gone:
            events.pop(k, None)
        events.update(made)
    save_events(apply)
    return errors


class Syncer:
    """Coalesces bursts of ledger writes into as few passes as needed."""

    def __init__(self, load, save_events, run=gws):
        self.load, self.save_events, self.run = load, save_events, run
        self._lock = threading.Lock()
        self._dirty = False
        self._running = False
        self.last_errors = []

    def kick(self):
        if not GWS and self.run is gws:
            return
        with self._lock:
            self._dirty = True
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            with self._lock:
                if not self._dirty:
                    self._running = False
                    return
                self._dirty = False
            try:
                self.last_errors = reconcile(self.load, self.save_events, self.run)
            except Exception as exc:
                self.last_errors = [str(exc)]
            for e in self.last_errors:
                sys.stderr.write("[gcal_sync] %s\n" % e)
