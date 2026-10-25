import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ai_help
import gcal_sync
import kit
import today_profile
from today_profile import PROFILE
import plugins

plugins.load(plugins.names_for(PROFILE))   # extras named in the profile, and the plugins behind its features
import ledger
import pomo_alerts

# anchors ride along with the rest of the day so the menubar app - which is
# the only part of this that is always running - can warn her before one lands.
# The date travels with them: if the planner has been shut since yesterday the
# list on disk is yesterday's, and firing those would be worse than silence.
DEFAULT_STATE = {"oneThing": "", "stackAfter": "", "done": False,
                 "anchors": [], "anchorsDate": "", "focus": ""}
STUDY_CACHE = os.path.expanduser("~/.study-cache.json")
SYNC_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "study_sync.py")
LEDGER_PATH = ledger.LEDGER
# Swappable so tests can drive the routes without opening apps.
KIT_RUNNER = subprocess.run
# The pomodoro's banners: the page reports each phase, the server keeps time.
POMO = pomo_alerts.Scheduler()

# A sync spawns a browser and walks six courses' worth of sources; it takes
# the better part of a minute. The planner must not be able to stack them up,
# so one runs at a time and the rest are told so rather than queued.
_sync = {"proc": None, "started": 0.0, "stamp": None}


def _cache_stamp():
    """When the cache was last written, as the sync itself records it."""
    try:
        with open(STUDY_CACHE) as fh:
            return json.load(fh).get("fetchedAt")
    except (IOError, ValueError):
        return None
_sync_lock = threading.Lock()


def sync_state():
    """running / idle, plus how long the current run has been going."""
    with _sync_lock:
        proc = _sync["proc"]
        if proc is not None and proc.poll() is None:
            return {"running": True, "seconds": round(time.time() - _sync["started"], 1)}
        code = proc.returncode if proc is not None else None
        out = {"running": False, "seconds": 0, "lastExit": code}
        # study_sync takes a file lock and exits 0 when a scheduled run already
        # holds it - nothing is re-read, but the exit code says success. The
        # cache stamp is the only honest evidence a pass actually happened, so
        # a run that left it untouched is reported as skipped rather than
        # letting the planner claim it checked.
        if proc is not None:
            out["skipped"] = (_sync["stamp"] is not None
                              and _cache_stamp() == _sync["stamp"])
        return out


def start_sync():
    """Kick off a full re-check. Returns (payload, started?)."""
    with _sync_lock:
        proc = _sync["proc"]
        if proc is not None and proc.poll() is None:
            return {"running": True, "alreadyRunning": True,
                    "seconds": round(time.time() - _sync["started"], 1)}, False
        try:
            # Same interpreter the LaunchAgent and menubar use, so a run
            # started from the planner behaves identically to a scheduled one.
            _sync["proc"] = subprocess.Popen(
                ["/usr/bin/python3", SYNC_SCRIPT],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _sync["started"] = time.time()
            _sync["stamp"] = _cache_stamp()
        except Exception as exc:
            return {"running": False, "error": str(exc)}, False
        return {"running": True, "alreadyRunning": False, "seconds": 0}, True


def load_state(path):
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_STATE)
    if not isinstance(data, dict):
        return dict(DEFAULT_STATE)
    merged = dict(DEFAULT_STATE)
    merged.update({k: data[k] for k in DEFAULT_STATE if k in data})
    return merged


def save_state(path, data):
    merged = dict(DEFAULT_STATE)
    if isinstance(data, dict):
        merged.update({k: data[k] for k in DEFAULT_STATE if k in data})
    with open(path, "w") as f:
        json.dump(merged, f)
    return merged


def format_title(one_thing, done, focus=""):
    """What the menubar shows.

    A running pomodoro outranks the day's one thing: it is what she is doing
    right now, and it is the only one of the two the Study page writes. The
    fallback keeps old days - and planner.html, which still writes oneThing
    and no focus - working untouched.
    """
    if focus:
        truncated = focus if len(focus) <= 20 else focus[:20] + "…"
        return "\U0001FAA9 " + truncated
    if not one_thing:
        return "\U0001FAA9"
    if done:
        return "\U0001FAA9 ✓"
    truncated = one_thing if len(one_thing) <= 20 else one_thing[:20] + "…"
    return "\U0001FAA9 " + truncated


def should_notify(one_thing, done, focus=""):
    if focus:
        return True
    return bool(one_thing) and not done


def _read_cache():
    try:
        with open(STUDY_CACHE) as fh:
            data = json.load(fh)
    except (IOError, ValueError):
        return {"courses": [], "errors": [], "fetchedAt": None}
    if not isinstance(data, dict):
        return {"courses": [], "errors": [], "fetchedAt": None}
    return data


def _course(course_key):
    # None means "no class" (the generic nook kit) - never scan for it, or a
    # cached course with a missing/null key would match by accident.
    if course_key is None:
        return {"key": None, "links": [], "kit": {}}
    for c in _read_cache().get("courses", []):
        if c.get("key") == course_key:
            return c
    return {"key": course_key, "links": [], "kit": {}}


def open_links(body):
    """Open urls in her real, signed-in Chrome.

    The planner runs in its own browser profile now, so a plain <a target=
    _blank> would open Brightspace logged out. Links go through kit._open,
    which hands them to the default profile."""
    urls = [u for u in (body.get("urls") or []) if isinstance(u, str) and u.startswith("http")]
    if not urls:
        return {"ok": False, "detail": "no urls"}
    ok, detail = kit._run_one(kit._open(urls), KIT_RUNNER)
    return {"ok": ok, "detail": detail, "opened": len(urls)}


def run_kit(body):
    cache = _read_cache()
    rows = kit.build_rows(_course(body.get("courseKey")),
                          playlist=cache.get("studyPlaylist"),
                          music_off=bool(body.get("musicOff")),
                          assignment=body.get("assignment"),
                          materials=body.get("materials"))
    return {"rows": kit.run_rows(rows, runner=KIT_RUNNER)}


_ledger_lock = threading.Lock()

# A copy of the planner's localStorage. Her history lives in the browser's
# profile and nowhere else, so this is both the backup and the way a fresh
# profile picks up where the last one left off.
STORAGE_BACKUP = os.path.expanduser("~/.today-planner-storage.json")


def load_storage():
    try:
        with open(STORAGE_BACKUP) as fh:
            data = json.load(fh)
    except (IOError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


_storage_lock = threading.Lock()


def save_storage(body):
    # Never replace a real backup with an empty one: a page that has not
    # finished restoring has nothing to say yet.
    if not body:
        return load_storage()
    # One temp name per write, under a lock: two heartbeats landing together
    # used to share "<backup>.tmp", so the second os.replace found it gone
    # (FileNotFoundError) and that backup was dropped.
    with _storage_lock:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORAGE_BACKUP), prefix=".today-planner-storage-")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(body, fh)
            os.replace(tmp, STORAGE_BACKUP)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return body

# When the planner last said "I am open". The menubar cannot always see the
# browser window (raising it takes an Automation grant that a launchd app is
# not always given), but it can always ask the page - which beats stacking a
# second window every time the Dock icon is pressed. Chrome throttles a hidden
# page's timers to about once a minute, so the window is generous.
_planner = {"seen": 0.0}
PLANNER_OPEN_WINDOW = 90


def note_planner(alive):
    _planner["seen"] = time.time() if alive else 0.0


def planner_status():
    age = time.time() - _planner["seen"]
    return {"open": age < PLANNER_OPEN_WINDOW, "age": round(age, 1)}


def planner_is_open(port=8765, timeout=0.5):
    """Ask whichever process owns the port - it may not be this one."""
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/ping" % port, timeout=timeout) as resp:
            return bool(json.load(resp).get("open"))
    except Exception:
        return False


def _save_cal_events(fn):
    with _ledger_lock:
        data = ledger.load(LEDGER_PATH)
        fn(data.setdefault("calEvents", {}))
        ledger.save(LEDGER_PATH, data)


# Planned sessions go to her Google Calendar in the background.
GCAL = gcal_sync.Syncer(lambda: ledger.load(LEDGER_PATH), _save_cal_events)


def apply_ledger(body):
    with _ledger_lock:
        data = ledger.apply_op(ledger.load(LEDGER_PATH), body if isinstance(body, dict) else {})
        saved = ledger.save(LEDGER_PATH, data)
    if isinstance(body, dict) and any(k in body for k in ("setPlan", "clearPlan", "removeTask")):
        GCAL.kick()
    return saved


def make_handler(state_path):
    class StateHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/study":
                # Always 200, even with no cache: the planner must render
                # normally when course data is missing, never show an error.
                # The page also gets the public part of the profile (school platform, study hours).
                try:
                    with open(STUDY_CACHE) as fh:
                        data = json.load(fh)
                except (IOError, ValueError):
                    data = {"courses": [], "errors": [], "fetchedAt": None}
                data["profile"] = today_profile.public(PROFILE)
                self._send_json(data)
                return
            if self.path == "/sync":
                self._send_json(sync_state())
                return
            if self.path == "/ledger":
                self._send_json(ledger.load(LEDGER_PATH))
                return
            if self.path == "/ping":
                self._send_json(planner_status())
                return
            if self.path == "/quiz-prep/start":
                # The Math page's Study Kit asks for this when Quiz Prep is down.
                try:
                    start_quiz_prep()
                    self._send_json({"started": True})
                except Exception as exc:
                    self._send_json({"started": False, "error": str(exc)[:200]})
                return
            if self.path == "/storage":
                self._send_json(load_storage())
                return
            if plugins.handle_get(self):
                return
            if self.path != "/state":
                self._send_json({"error": "not found"}, status=404)
                return
            self._send_json(load_state(state_path))

        def do_POST(self):
            if self.path == "/sync":
                payload, _started = start_sync()
                self._send_json(payload)
                return
            if self.path.startswith("/ping"):
                # sendBeacon on pagehide can only send a body, so "bye" rides
                # in the query: /ping?bye. No body and no JSON either way.
                note_planner(not self.path.endswith("?bye"))
                self._send_json(planner_status())
                return
            routes = {"/state": lambda b: save_state(state_path, b),
                      "/ledger": apply_ledger,
                      "/storage": save_storage,
                      # Claude in the session: open gathers once (can take
                      # ~30s the first time), chat runs one headless turn
                      "/ai/open": ai_help.open_for,
                      "/ai/chat": ai_help.chat_for,
                      "/ai/terminal": ai_help.terminal_for,
                      "/kit/run": run_kit,
                      "/kit/open": open_links,
                      "/kit/music": lambda b: kit.run_music(
                          b.get("action", "pause"), _read_cache().get("studyPlaylist"), runner=KIT_RUNNER),
                      "/kit/stop": lambda b: {"results": kit.run_stop(runner=KIT_RUNNER)},
                      "/pomo": lambda b: POMO.set(b) if b.get("phase") in ("work", "break") else POMO.clear()}
            routes.update(plugins.post_routes())   # personal extras (internships, adviser…) when installed
            handler = routes.get(self.path)
            if handler is None:
                self._send_json({"error": "not found"}, status=404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length else b"{}"
            try:
                incoming = json.loads(raw)
            except json.JSONDecodeError:
                incoming = {}
            if not isinstance(incoming, dict):
                incoming = {}
            # Claude and anything a plugin marks as keyed (agents with shell access) need the planner's key
            if (self.path.startswith("/ai/") or any(self.path.startswith(k) for k in plugins.keyed_routes())) \
                    and not ai_help.authorized(incoming):
                # any site can reach this port; only the planner the menubar
                # opened holds the token
                self._send_json({"error": "reopen the planner from the menu bar"}, status=403)
                return
            try:
                result = handler(incoming)
            except ai_help.Unavailable as exc:
                self._send_json({"error": str(exc)}, status=404)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            except Exception as exc:
                sys.stderr.write("[state_server] POST %s: %r\n" % (self.path, exc))
                self._send_json({"error": str(exc)}, status=500)
                return
            self._send_json(result)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    return StateHandler


QUIZ_PREP_DIR = os.path.expanduser(os.environ.get("QUIZ_PREP_DIR") or PROFILE["quizPrep"]["dir"]
                                   or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quiz-prep"))
QUIZ_PREP_PORT = 3123


def start_quiz_prep():
    """Launch the Quiz Prep server in the background. Never raises: the menu
    bar matters more than the study kit, and KeepAlive would crash-loop."""
    try:
        import socket
        if not os.path.exists(os.path.join(QUIZ_PREP_DIR, "server.js")):
            return
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", QUIZ_PREP_PORT)) == 0:
                return  # already up
        log = open(os.path.expanduser("~/.quiz-prep.log"), "a")
        subprocess.Popen(
            ["/bin/bash", "-c",
             'export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; cd "$1" && '
             '{ [ -d node_modules/pdfjs-dist ] || npm install --silent --no-audit --no-fund; } && while true; do node server.js; sleep 1; done',
             "quiz-prep", QUIZ_PREP_DIR],
            stdout=log, stderr=log, start_new_session=True)
    except Exception:
        pass


def start_server(state_path, port=8765, host="127.0.0.1"):
    handler = make_handler(state_path)
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
