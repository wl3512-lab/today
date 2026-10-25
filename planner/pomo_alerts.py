"""Banners for the pomodoro, fired from the menubar rather than the page.

The planner spends most of a session behind whatever she is studying, and
Chrome slows a hidden page's timers to about once a minute - so the page is
the wrong thing to trust with "your break starts in two minutes". The page
tells the server each time a phase begins (what, and when it ends); the
server, which is always running, owns the clock from there.

Each phase schedules a heads-up shortly before it ends and a banner as it
ends. A work phase also pre-schedules the break that follows it, so the
banners still land if the planner window is closed mid-block; a fresh
snapshot from the page replaces whatever was pending.

Delivery, and why it is not just a notification
-----------------------------------------------
`display notification` posts under Script Editor's identity, and Script Editor
has no entry in com.apple.ncprefs - macOS registers 123 apps on this machine
and that is not one of them. An unregistered sender still gets *delivered*:
the alert lands in Notification Center and stacks up there unread. It is
simply never drawn on screen as a banner. That is the whole bug - the reminders
were arriving the entire time, silently, where nobody was looking.

Nothing here can register Script Editor, so the phase boundaries - the two
moments that actually have to interrupt - do not rely on a banner at all. They
also raise a modal alert, which needs no notification permission and has to be
dismissed. The lead-ins stay soft: a sound and a notification, because a
warning that steals focus mid-block is worse than no warning.

Every alert carries a sound, so a phase change is audible even when the screen
is on another Space and a modal cannot be seen.
"""
import json
import subprocess
import threading

WORK_LEAD_SEC = 2 * 60      # "break in 2 minutes"
BREAK_LEAD_SEC = 60         # "break ends in 1 minute"
WORK_MIN = 25

# How an alert is allowed to interrupt.
SOFT = "soft"   # sound + notification: a warning, not a summons
HARD = "hard"   # the above, plus a modal that must be dismissed

SOFT_SOUND = "Glass"
HARD_SOUND = "Hero"

# The modal closes itself so a missed break can never wedge a dialog over the
# screen for the rest of the day.
ALERT_SECONDS = 45


def _osa(script, timeout):
    subprocess.run(["/usr/bin/osascript", "-e", script],
                   capture_output=True, timeout=timeout)


def banner(title, msg, subtitle="", kind=SOFT):
    """Announce a phase change.

    Both halves are attempted independently: a modal still goes up if the
    notification was swallowed, which on this machine is exactly what happens.
    """
    try:
        script = "display notification %s with title %s" % (json.dumps(msg), json.dumps(title))
        if subtitle:
            script += " subtitle %s" % json.dumps(subtitle)
        script += " sound name %s" % json.dumps(HARD_SOUND if kind == HARD else SOFT_SOUND)
        _osa(script, 10)
    except Exception:
        pass
    if kind != HARD:
        return
    try:
        body = (subtitle + "\n\n" + msg) if subtitle else msg
        _osa("display alert %s message %s giving up after %d"
             % (json.dumps(title), json.dumps(body), ALERT_SECONDS),
             ALERT_SECONDS + 15)
    except Exception:
        pass


def _mins(n):
    n = int(n or 0)
    return "%d minute%s" % (n, "" if n == 1 else "s")


def alerts_for(snap, now_ms):
    """The banners a phase snapshot calls for, as (fire_at_ms, title, body,
    kind), soonest first. Only ones still in the future; nothing for idle."""
    if not isinstance(snap, dict):
        return []
    phase = snap.get("phase")
    try:
        end = float(snap.get("endAt") or 0)
    except (TypeError, ValueError):
        return []
    if phase not in ("work", "break") or end <= 0:
        return []
    subject = (snap.get("subject") or "").strip()
    on = (" on " + subject) if subject else ""
    out = []
    if phase == "work":
        brk = int(snap.get("nextBreakMin") or 5)
        long_break = brk >= 15
        out.append((end - WORK_LEAD_SEC * 1000, "Break in 2 minutes",
                    "Find a stopping point" + on + ".", SOFT))
        out.append((end, "Long break" if long_break else "Break time",
                    _mins(brk) + ". Step away from the screen.", HARD))
        # the break that follows, in case the page is closed when it starts
        brk_end = end + brk * 60000
        out.append((brk_end - BREAK_LEAD_SEC * 1000, "Break ends in 1 minute",
                    "Back" + on + " next.", SOFT))
        # after the fourth block the break closes the set; the page says so up front
        last = bool(snap.get("lastBlock"))
        out.append((brk_end, "Set done" if last else "Break's over",
                    "Four down. That was a whole set." if last
                    else _mins(snap.get("nextWorkMin") or WORK_MIN) + on + ". Tap the ring if the planner is closed.",
                    HARD))
    else:
        out.append((end - BREAK_LEAD_SEC * 1000, "Break ends in 1 minute",
                    "Back" + on + " next.", SOFT))
        if snap.get("setDone"):
            out.append((end, "Set done", "Four down. That was a whole set.", HARD))
        else:
            out.append((end, "Break's over",
                        _mins(snap.get("nextWorkMin") or WORK_MIN) + on + ". Tap the ring if the planner is closed.",
                        HARD))
    return [a for a in out if a[0] > now_ms]


class Scheduler:
    """One pending plan at a time; a new snapshot replaces it entirely."""

    def __init__(self, notify=banner, timer=threading.Timer, now_ms=None):
        self._notify = notify
        self._timer = timer
        self._now = now_ms or (lambda: __import__("time").time() * 1000)
        self._pending = []
        self._lock = threading.Lock()

    def set(self, snap):
        now = self._now()
        alerts = alerts_for(snap, now)
        with self._lock:
            self._cancel_locked()
            for at, title, body, kind in alerts:
                t = self._timer((at - now) / 1000.0, self._notify, (title, body, "", kind))
                t.daemon = True
                t.start()
                self._pending.append((at, title, t))
        return {"scheduled": [{"at": at, "title": title} for at, title, _ in self._pending]}

    def clear(self):
        with self._lock:
            self._cancel_locked()
        return {"scheduled": []}

    def _cancel_locked(self):
        for _, _, t in self._pending:
            try:
                t.cancel()
            except Exception:
                pass
        self._pending = []

    def pending(self):
        with self._lock:
            return [(at, title) for at, title, _ in self._pending]
