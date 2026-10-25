"""Sessions started straight from the menubar, with nothing to pick first.

The planner's nook starts from an assignment. These start from a click:
a study block tagged with a class and one line of what she is doing
("reading ch. 4", "SwiftUI practice"), quiet reading with its own playlist,
or a timed stretch of journalling on paper. Each one turns the Study focus
on, runs a countdown in the menubar, and logs its minutes to the ledger so
the History page can show where the time went.
"""
import json
import os
import re

import kit
from today_profile import PROFILE
import pomo_alerts

COURSES = os.path.expanduser(PROFILE["coursesPath"])
# The session that is running, so a relaunch of the menubar app (KeepAlive
# after a crash, a kickstart after an edit) picks the clock back up instead of
# dropping it and logging nothing.
SESSION_FILE = os.path.expanduser("~/.today-quick-session.json")
# A default instrumental Spotify playlist for reading. Reading plays in the
# Spotify app (study stays SoundCloud); `readingPlaylist` in ~/.courses.json
# overrides it with a spotify: uri or an open.spotify.com link.
READING_PLAYLIST = "spotify:playlist:37i9dQZF1DX7hmlhGsyxU0"

MODES = {
    "study": {"minutes": 25, "icon": "\U0001F4DA", "playlist": "studyPlaylist"},
    "reading": {"minutes": 45, "icon": "\U0001F4D6", "playlist": "readingPlaylist"},
    # on paper - no tabs, no music, just the quiet and a clock
    "journal": {"minutes": 15, "icon": "✏️", "playlist": None},
}
NOTE_MAX = 120


def load_registry(path=COURSES):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def classes(registry):
    """(key, short name) for each class, in registry order."""
    out = []
    for c in registry.get("courses") or []:
        if isinstance(c, dict) and c.get("key"):
            out.append((c["key"], c.get("short") or c.get("name") or c["key"]))
    return out


def spotify_uri(value):
    """spotify:playlist:ID from either that uri or an open.spotify.com link."""
    value = str(value or "").strip()
    if value.startswith("spotify:playlist:"):
        return value
    m = re.match(r"https?://open\.spotify\.com/playlist/([A-Za-z0-9]+)", value)
    return "spotify:playlist:" + m.group(1) if m else None


def playlist_for(mode, registry):
    field = MODES[mode]["playlist"]
    if not field:
        return None
    if mode == "reading":
        return spotify_uri(registry.get(field)) or READING_PLAYLIST
    url = registry.get(field)
    return url if kit.web_playlist(url) else None


def spotify_play_cmd(uri):
    # unlike a SoundCloud tab, the app can be told to start playing
    return ["/usr/bin/osascript", "-e", 'tell application "Spotify" to play track "%s"' % uri]


def stop_cmds(mode):
    cmds = list(kit.stop_cmds())
    if mode == "reading":
        cmds.append(["/usr/bin/osascript", "-e", 'tell application "Spotify" to pause'])
    return cmds


def start_cmds(mode, registry):
    """Focus on first, so nothing that opens after it can ping her."""
    cmds = [["shortcuts", "run", kit.FOCUS_ON]]
    url = playlist_for(mode, registry)
    if url and url.startswith("spotify:"):
        # opening needs no permission; playing needs an Automation grant
        # macOS may never offer a launchd app - if it fails, one click on play
        cmds.append(["open", url])
        cmds.append(spotify_play_cmd(url))
    elif url:
        cmds.append(kit.music_cmd("play", url))
    return cmds


def label(mode, short=None):
    if mode == "study":
        return short or "Study"
    return {"reading": "Reading", "journal": "Journal"}[mode]


def countdown_title(mode, short, seconds_left):
    """What the menubar shows while a session runs: icon, what, minutes left."""
    mins = max(0, int(seconds_left + 59) // 60)       # round up: 0:30 left reads "1m"
    return "%s %s %dm" % (MODES[mode]["icon"], label(mode, short), mins)


def start_alert(mode, short, minutes, results):
    """(title, message, kind) for the moment a session starts.

    `results` are (cmd, ok, detail) for each start command. A start always
    makes a sound: the countdown is in a menubar item Ice hides, so without
    one a press that worked looks exactly like one that did not. (A Dock
    badge would not show either: macOS only draws badges for apps registered
    for notifications, and this bundle never has been.) If Focus did not
    come on, that has to interrupt - quiet is the whole point of these
    sessions, and a failing Shortcut otherwise fails in silence.
    """
    title = "%s · %d min" % (label(mode, short), minutes)
    for cmd, ok, detail in results:
        if ok or cmd != ["shortcuts", "run", kit.FOCUS_ON]:
            continue
        if "find shortcut" in detail.lower():
            msg = ('The timer is running, but Focus didn\'t turn on: this Mac has no '
                   'Shortcut called "%s". In Shortcuts, make "%s" with one Set Focus '
                   'action (Do Not Disturb, Turn On) and "%s" with the same action set '
                   'to Turn Off.' % (kit.FOCUS_ON, kit.FOCUS_ON, kit.FOCUS_OFF))
        else:
            msg = "The timer is running, but Focus didn't turn on: %s" % detail
        return title, msg, pomo_alerts.HARD
    return title, "Timer started. An alert comes up when it's done.", pomo_alerts.SOFT


def save_session(session, path=None):
    """Remember the running session, or forget it (None)."""
    path = path or SESSION_FILE
    try:
        if session is None:
            if os.path.exists(path):
                os.remove(path)
            return
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(session, fh)
        os.replace(tmp, path)
    except OSError:
        pass                     # losing this costs a relaunch's resume, never the session


def load_session(path=None):
    """The saved session, or None if there is none or it is not one."""
    try:
        with open(path or SESSION_FILE) as fh:
            s = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(s, dict) or s.get("mode") not in MODES:
        return None
    try:
        s["started"], s["ends"], s["minutes"] = float(s["started"]), float(s["ends"]), int(s["minutes"])
    except (KeyError, TypeError, ValueError):
        return None
    for k in ("key", "short"):
        s.setdefault(k, None)
    s.setdefault("note", "")
    return s


def elapsed_minutes(started, now, planned):
    """Whole minutes worked, never more than the block was for."""
    return max(0, min(planned, int(round((now - started) / 60.0))))


def session_op(mode, minutes, course_key=None, note=""):
    """The ledger op for a finished session."""
    s = {"minutes": minutes, "courseKey": course_key if mode == "study" else None,
         "kind": mode}
    note = (note or "").strip()[:NOTE_MAX]
    if note:
        s["note"] = note
    return {"addSession": s}
