import os
import subprocess
import sys
import threading
import rumps

import datetime
import json
import re
import time

import ai_help
import kit
import planner_guard
import planner_window
import pomo_alerts
import quick
from state_server import (apply_ledger, format_title, load_state, planner_is_open,
                          should_notify, start_server)

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Which page to open, one line, e.g. "planner-dark.html". Absent means the
# original planner.
PAGE_FILE = ".planner-page"


def planner_path(page=None, app_dir=None):
    """Which planner the menubar opens.

    The React rebuild ships as planner-next.html beside the original. Both are
    opened from disk, so they share the file:// origin and therefore one
    localStorage - switching between them migrates nothing and loses nothing.

    To go back to the original:  TODAY_PLANNER_PAGE=planner.html

    A page that is not there falls back to planner.html rather than opening a
    blank window: a missing build should cost the new features, not the planner.
    """
    app_dir = app_dir or APP_DIR
    if page is None:
        # A file, not just an environment variable: the menubar app is launched
        # through `open`, which strips the environment, so TODAY_PLANNER_PAGE
        # alone never reaches it. The file is what actually works; the variable
        # is kept for running app.py directly from a shell.
        try:
            with open(os.path.join(app_dir, PAGE_FILE)) as fh:
                page = fh.read().strip() or None
        except OSError:
            page = None
    page = page or os.environ.get("TODAY_PLANNER_PAGE") or "planner.html"
    path = os.path.join(app_dir, page)
    if not os.path.exists(path):
        path = os.path.join(app_dir, "planner.html")
    return path


PLANNER_PATH = planner_path()


def planner_url(path=None):
    """The planner's address, stamped with the file's modification time.

    Chrome caches file:// URLs hard, and nothing about a local edit tells it to
    look again - so an edited planner kept opening as the version it had first
    seen, which is indistinguishable from the edit never happening. The stamp
    changes whenever the file does, which is a different URL, which is a cache
    miss. Read at open time, not import time, so a file edited while the app is
    running still comes up fresh.
    """
    path = path or planner_path()
    try:
        stamp = int(os.path.getmtime(path))
    except OSError:
        stamp = 0
    # t: the key to the server's /ai/* routes (see ai_help.token) - the page
    # keeps it, since only a window the menubar opened can know it
    return "file://" + path + "?v=" + str(stamp) + "&t=" + ai_help.token()


PLANNER_URL = planner_url(PLANNER_PATH)
STATE_PATH = os.path.join(APP_DIR, "state.json")
STATE_PORT = 8765

# rumps creates its status item unnamed, so macOS files it in a generic
# "Item-N" slot. Those slots are shared, and Control Center had every one of
# them persisted as hidden, which is why the icon kept vanishing. Naming the
# item gives it its own preference key that survives relaunches.
STATUS_ITEM_NAME = "TodayPlanner"
# Which warnings have already gone out, so a relaunch mid-afternoon does not
# replay the morning's. Keyed by day, and only today's day is ever kept.
FIRED_PATH = os.path.expanduser("~/.today-anchors-fired.json")
LEAD_MINUTES = 30
HEART = "\U0001FAA9"


# "9PM", "9 pm", "9:45pm", "21:00", "2pm" - she types the time the way she
# would say it, and the field has never demanded a format. Anything that is
# not a time at all (the "-" placeholder) simply gets no reminder.
_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m?\.?\s*$", re.I)


def parse_anchor_time(text, today):
    """A datetime for today, or None if this is not a time."""
    if not text:
        return None
    m = _TIME.match(text)
    if m:
        hour, minute, half = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if not (1 <= hour <= 12) or minute > 59:
            return None
        if half == "a":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    else:
        m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", text)
        if not m:
            return None
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            return None
    return datetime.datetime.combine(today, datetime.time(hour, minute))


def notify(title, msg, subtitle=""):
    """Post a banner the way the sync does.

    rumps.notification goes through NSUserNotificationCenter, which quietly
    drops everything from a bundle macOS has not registered - it returns
    cleanly and nothing appears, which is the worst possible failure for a
    reminder. osascript is the call study_sync has always used; the helper
    lives in pomo_alerts so the pomodoro's banners are the same kind.
    """
    pomo_alerts.banner(title, msg, subtitle)


def _same_day(stamp, today):
    """Compare the planner's day key to a date.

    The planner writes "2026-9-11", unpadded - it has always been the key its
    saved days are filed under, so it cannot be reformatted without orphaning
    every day already stored. Normalise here instead of there.
    """
    if not stamp:
        return True          # no date claimed: trust the list
    try:
        y, m, d = (int(x) for x in str(stamp).split("-"))
    except ValueError:
        return False
    return (y, m, d) == (today.year, today.month, today.day)


def _load_fired(daykey):
    try:
        with open(FIRED_PATH) as fh:
            data = json.load(fh)
    except (IOError, ValueError):
        return set()
    if not isinstance(data, dict) or data.get("date") != daykey:
        return set()
    return set(data.get("keys") or [])


def _save_fired(daykey, keys):
    try:
        with open(FIRED_PATH, "w") as fh:
            json.dump({"date": daykey, "keys": sorted(keys)}, fh)
    except IOError:
        pass


def _install_dock():
    """Put Today in the Dock as well as the menu bar.

    The status item itself is healthy - it reports visible=True at x=-4020,
    which is where Ice (the menu bar manager, AutoRehide on) parks anything it
    has filed into the collapsed section. So the icon is not lost, it is one
    chevron click away, which is one click too many for the mornings this app
    exists for. The Dock tile is a second entry point that does not depend on
    revealing Ice first.

    Deliberately run AFTER the status bar is up: flipping activation policy
    first is exactly what confuses this app's bundle identity and loses the
    status item altogether.
    """
    import objc
    from AppKit import (NSApplication, NSApplicationActivationPolicyRegular,
                        NSImage, NSMakeSize, NSMakePoint, NSFont,
                        NSFontAttributeName, NSString)
    from rumps.rumps import NSApp as Delegate

    ns = NSApplication.sharedApplication()
    ns.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    # The same heart the menu bar uses, so the two read as one app. Centred by
    # measurement rather than by eye: a glyph's drawing origin is its baseline,
    # not its box, so a hand-picked point sits noticeably high in the tile.
    attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(340)}
    glyph = NSString.stringWithString_(HEART)
    box = glyph.sizeWithAttributes_(attrs)
    img = NSImage.alloc().initWithSize_(NSMakeSize(512, 512))
    img.lockFocus()
    glyph.drawAtPoint_withAttributes_(
        NSMakePoint((512 - box.width) / 2.0, (512 - box.height) / 2.0), attrs)
    img.unlockFocus()
    ns.setApplicationIconImage_(img)

    # A Dock icon that does nothing on click is furniture. This one opens the
    # planner, which is the only thing anybody wants from it.
    sel = "applicationShouldHandleReopen:hasVisibleWindows:"
    if not Delegate.instancesRespondToSelector_(sel):
        def _reopen(self, sender, has_windows):
            open_as_app_window()
            return True
        objc.classAddMethods(Delegate, [objc.selector(
            _reopen, selector=sel.encode(), signature=b"B@:@B")])


def _name_status_item():
    """Create the status bar item with a stable autosave name."""
    original = rumps.rumps.NSApp.initializeStatusBar

    def initializeStatusBar(self):
        original(self)
        try:
            self.nsstatusitem.setAutosaveName_(STATUS_ITEM_NAME)
            self.nsstatusitem.setVisible_(True)
        except Exception:
            pass  # never let cosmetics stop the app from launching

        try:
            _install_dock()
        except Exception as exc:
            # KeepAlive is set: raising here would crash-loop the menu bar.
            with open("/tmp/today_pos.log", "a") as fh:
                fh.write("dock setup failed: %r\n" % (exc,))

        def _report():
            import time
            for t in (3, 8, 15):
                time.sleep(t if t == 3 else t - 3)
                try:
                    w = self.nsstatusitem.button().window()
                    f = w.frame()
                    with open("/tmp/today_pos.log", "a") as fh:
                        fh.write("t=%ss x=%s y=%s w=%s vis=%s\n" % (
                            t, f.origin.x, f.origin.y, f.size.width, w.isVisible()))
                except Exception as e:
                    with open("/tmp/today_pos.log", "a") as fh:
                        fh.write("t=%ss failed: %r\n" % (t, e))

        threading.Thread(target=_report, daemon=True).start()

    rumps.rumps.NSApp.initializeStatusBar = initializeStatusBar


BROWSERS = [
    "/Applications/Google Chrome.app",
    "/Applications/Microsoft Edge.app",
    "/Applications/Brave Browser.app",
]
# The planner runs in its own browser profile, which means its own process:
# one whose only window is the planner. That is what makes "is it open" and
# "bring it forward" answerable without asking the browser anything. The old
# way - an AppleScript walk over Chrome's windows - needs an Automation grant
# that macOS never offered this app (it runs from launchd), so every press
# fell through to "open another one".
PLANNER_PROFILE = os.path.expanduser("~/.today-planner-chrome")


def _planner_browser_pid():
    """The main process of the browser instance that owns the planner profile.

    Helpers (renderers, GPU) carry the same --user-data-dir; they also carry
    --type=, and the browser process is the one that does not.
    """
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    marker = "--user-data-dir=" + PLANNER_PROFILE
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if marker in cmd and "--type=" not in cmd and pid.isdigit():
            return int(pid)
    return None


def _activate(pid):
    """Bring that process's windows forward. True if macOS agreed."""
    try:
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        return bool(app) and bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
    except Exception as exc:
        sys.stderr.write("[Today] activate %s: %r\n" % (pid, exc))
        return False


def _focus_planner_window():
    """Raise the planner's own window, not just its browser.

    Activating the process brings Chrome forward, and if any other Chrome
    window is frontmost that is the one that appears - the planner stays
    behind it and the menu bar looks broken. This asks for the window whose
    url is the planner and puts that one at index 1.
    """
    page = os.path.basename(PLANNER_PATH)
    script = (
        'tell application "Google Chrome"\n'
        '  set found to false\n'
        '  repeat with w in windows\n'
        '    repeat with t in tabs of w\n'
        '      if URL of t contains "%s" then\n'
        '        set index of w to 1\n'
        '        set found to true\n'
        '        exit repeat\n'
        '      end if\n'
        '    end repeat\n'
        '    if found then exit repeat\n'
        '  end repeat\n'
        '  if found then activate\n'
        '  return found\n'
        'end tell' % page
    )
    try:
        out = subprocess.run(["/usr/bin/osascript", "-e", script],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() == "true"
    except Exception as exc:
        sys.stderr.write("[Today] focus window: %r\n" % (exc,))
        return False


def _planner_windows(pid):
    """(real windows, of those how many are on screen) for the planner's Chrome.

    Quartz lists windows by owning process with no permission prompt, which
    AppleScript cannot do for a second Chrome instance. Chrome also owns
    thin strips and popups on layer 0, so only something window-sized counts.
    The strips are 33pt tall or 44pt wide; the planner is often kept small
    (529x399 seen), so the floor sits well below any real window.

    On screen matters because a minimized window still counts as open, and
    activating Chrome does not un-minimize it: Open Planner then did nothing
    at all that she could see.
    """
    try:
        import Quartz
        rows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID) or []
    except Exception as exc:
        sys.stderr.write("[Today] window list: %r\n" % (exc,))
        return 0, 0
    total = visible = 0
    for w in rows:
        b = w.get("kCGWindowBounds") or {}
        if (w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0
                and b.get("Width", 0) >= 200 and b.get("Height", 0) >= 150):
            total += 1
            if w.get("kCGWindowIsOnscreen"):
                visible += 1
    return total, visible


def _planner_window_count(pid):
    return _planner_windows(pid)[0]


def _quit_browser(pid, wait=5.0):
    """Quit the planner's own Chrome (it holds nothing but the planner; the
    day lives in the server and localStorage). True once it has exited."""
    try:
        from AppKit import NSRunningApplication
        app_ = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if not app_:
            return True
        app_.terminate()
        end = time.time() + wait
        while time.time() < end:
            if app_.isTerminated():
                return True
            time.sleep(0.2)
        app_.forceTerminate()
        time.sleep(0.5)
        return app_.isTerminated()
    except Exception as exc:
        sys.stderr.write("[Today] quit planner chrome %s: %r\n" % (pid, exc))
        return False


def open_as_app_window():
    """Go to the planner, in its own window (see planner_window.py).

    The Chrome window below stays as the fallback: no PyObjC WebKit, or a
    .planner-in-chrome file asking for it back.
    """
    native = planner_window.wanted()
    sys.stderr.write("[Today] open planner (%s)\n" % ("own window" if native else "Chrome"))
    if native:
        try:
            planner_window.show(PLANNER_PATH)
            return
        except Exception as exc:          # never leave her with no planner at all
            sys.stderr.write("[Today] native planner window: %r\n" % (exc,))
    open_in_browser()


def open_in_browser():
    """Go to the planner: raise the one that is open, open one only if none is.

    Opening unconditionally assumed Chrome would reuse the window for a url
    it already had. It does not - every --app launch makes a new window, and
    the url carries a cache stamp besides - so each press of Open Planner
    left another planner behind. The planner lives in its own Chrome
    instance with its own profile, so that instance only ever holds planner
    windows, and activating it by process brings the planner forward.
    """
    pid = _planner_browser_pid()
    if pid:
        total, visible = _planner_windows(pid)
        if visible and _activate(pid):
            return
        if total and not visible:
            # minimized or stranded on another Space: activating shows nothing,
            # and a second --app launch would leave the hidden one behind
            _quit_browser(pid)
    for path in BROWSERS:
        if not os.path.exists(path):
            continue
        # -n starts a new process; if one already owns the profile it hands
        # this command line over and exits, and that one opens the window.
        subprocess.Popen([
            "open", "-na", path,
            "--args", "--user-data-dir=" + PLANNER_PROFILE,
            "--no-first-run", "--no-default-browser-check",
            # planner_guard reads this to keep the instance to the one page
            "--remote-debugging-port=%d" % planner_guard.PORT,
            "--app=" + planner_url(),
        ])
        return
    subprocess.Popen(["open", planner_url()])


def run_cmds(cmds, runner=subprocess.run, log=None):
    """Run each command; [(cmd, ok, detail)], with every failure logged.

    These used to be fired and forgotten, so a missing "Study" Shortcut failed
    on every session start for weeks without a line anywhere.
    """
    log = log or sys.stderr.write
    results = []
    for c in cmds:
        ok, detail = kit._run_one(c, runner)
        if not ok:
            log("[Today] %s failed: %s\n" % (" ".join(c[:3]), detail))
        results.append((c, ok, detail))
    return results



class TodayApp(rumps.App):
    def __init__(self):
        super().__init__("Today", title="\U0001FAA9", quit_button="Quit")
        self.session = None
        self.end_item = rumps.MenuItem("End session", callback=self.end_session)
        self.menu = [self._study_menu(),
                     rumps.MenuItem("Reading", callback=lambda _: self.start_session("reading")),
                     rumps.MenuItem("Journalling", callback=lambda _: self.start_session("journal")),
                     self.end_item, None,
                     "Open Planner", "Refresh classes"]
        self._show_end(False)
        self.session_timer = rumps.Timer(self.tick_session, 15)
        # A stale instance may still hold the port. The menu bar item matters
        # more than the sync server, so never let this stop the app launching
        # (with KeepAlive set, raising here would crash-loop forever).
        try:
            self._server, self._server_thread = start_server(STATE_PATH, port=STATE_PORT)
        except OSError:
            self._server = self._server_thread = None
        # Quiz Prep (~/Desktop/quiz-prep) powers the Study Kit inside the Math
        # class page. Start it alongside Today unless it is already running.
        try:
            from state_server import start_quiz_prep
            start_quiz_prep()
        except Exception:
            pass
        self.title_timer = rumps.Timer(self.update_title, 30)
        self.title_timer.start()
        self.nudge_timer = rumps.Timer(self.maybe_notify, 1800)
        self.nudge_timer.start()
        # Refresh course data in the background so the planner never waits on
        # a browser spawn. Failures are swallowed: KeepAlive is set, so an
        # exception here would crash-loop the menubar.
        # A LaunchAgent owns the real schedule (every 2h). This is only a
        # backstop for when that is unloaded - two syncs 15 min apart would
        # spawn browsers far more often than the data ever changes.
        self.study_timer = rumps.Timer(self.sync_study, 21600)
        self.study_timer.start()
        # 60s poll against a 120s window, so a tick that runs late still lands.
        self.anchor_timer = rumps.Timer(self.check_anchors, 60)
        self.anchor_timer.start()
        # Links clicked in other apps land in the planner's Chrome whenever her
        # real Chrome is closed (macOS sees both as "Google Chrome"). This
        # closes them there and reopens them in the real one, and folds
        # duplicate planner pages back to one. See planner_guard.py.
        self.guard = planner_guard.Guard(os.path.basename(PLANNER_PATH), self._forward_links)
        self.guard_timer = rumps.Timer(self.guard_tick, 2)
        self.guard_timer.start()
        try:
            self._resume_session()
        except Exception as exc:          # KeepAlive: a bad saved session must not crash-loop
            sys.stderr.write("[Today] resume session: %r\n" % (exc,))

    def _forward_links(self, urls):
        try:
            subprocess.Popen(kit._open(urls))
        except Exception as exc:
            sys.stderr.write("[Today] forward %d links: %r\n" % (len(urls), exc))

    def guard_tick(self, _timer):
        try:
            done = self.guard.poll()
            if done and done[0]:
                sys.stderr.write("[Today] guard closed %d, forwarded %d\n" % (len(done[0]), len(done[1])))
        except Exception as exc:          # KeepAlive: never let a poll crash the menubar
            sys.stderr.write("[Today] guard: %r\n" % (exc,))

    def check_anchors(self, _timer):
        """Warn 30 minutes before a time she committed to.

        The planner is a browser page she may well have closed, so the warning
        cannot live there. This runs in the menubar app, which is always up.

        It only ever looks backward across the poll interval, never forward:
        an anchor added after its own warning time has already passed has
        missed the point and stays quiet rather than firing immediately.
        """
        try:
            state = load_state(STATE_PATH)
            anchors = state.get("anchors") or []
            if not anchors:
                return
            now = datetime.datetime.now()
            daykey = now.strftime("%Y-%m-%d")
            # Stale list from a day the planner was never opened on.
            if not _same_day(state.get("anchorsDate"), now.date()):
                return
            fired = _load_fired(daykey)
            changed = False
            for a in anchors:
                when = parse_anchor_time(a.get("time"), now.date())
                if not when:
                    continue
                warn_at = when - datetime.timedelta(minutes=LEAD_MINUTES)
                key = "%s|%s" % (a.get("time"), a.get("what"))
                if key in fired:
                    continue
                delta = (now - warn_at).total_seconds()
                if 0 <= delta < 120:
                    notify("In %d minutes" % LEAD_MINUTES,
                           a.get("what") or "",
                           "at %s" % (a.get("time") or ""))
                    fired.add(key)
                    changed = True
            if changed:
                _save_fired(daykey, fired)
        except Exception:
            # KeepAlive is set; an exception here would crash-loop the menubar.
            pass

    def sync_study(self, _timer):
        try:
            subprocess.Popen(
                ["/usr/bin/python3", os.path.join(APP_DIR, "study_sync.py")],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    @rumps.clicked("Refresh classes")
    def refresh_classes(self, _):
        self.sync_study(None)
        notify("Classes", "Refreshing course data\u2026")

    @rumps.clicked("Open Planner")
    def open_planner(self, _):
        open_as_app_window()

    def _todays_state(self):
        # The planner pushes its day whenever it is open; if it is not open at
        # midnight nothing tells the menubar the One Thing has expired, and it
        # would keep showing (and nagging about) yesterday's task.
        #
        # focus goes stale the same way, and worse: a block that was still
        # running when Chrome quit never got to post its own end, so its subject
        # sits in state.json indefinitely. Without clearing it here the menubar
        # would nudge "Still on it?" about a block abandoned the day before.
        state = load_state(STATE_PATH)
        if not _same_day(state.get("anchorsDate"), datetime.date.today()):
            state = dict(state, oneThing="", done=False, focus="")
        return state

    # --- sessions started from the menu (see quick.py) ---

    def _study_menu(self):
        menu = rumps.MenuItem("Quick study sesh")
        for key, short in quick.classes(quick.load_registry()):
            menu.add(rumps.MenuItem(short, callback=self._study_picker(key, short)))
        menu.add(rumps.MenuItem("Something else", callback=self._study_picker(None, None)))
        return menu

    def _study_picker(self, key, short):
        def pick(_):
            try:
                from AppKit import NSApp
                NSApp.activateIgnoringOtherApps_(True)   # else the prompt opens behind her work
            except Exception:
                pass
            answer = rumps.Window(
                message="What are you working on? (reading, SwiftUI practice\u2026)\n"
                        "Leave it blank to just start.",
                title=short or "Quick study sesh", default_text="",
                ok="Start", cancel="Cancel", dimensions=(280, 24)).run()
            if answer.clicked:
                self.start_session("study", key, short, answer.text)
        return pick

    def _show_end(self, shown):
        try:
            self.end_item._menuitem.setHidden_(not shown)
        except Exception:
            pass

    def _run_bg(self, cmds, then=None):
        """Run cmds off the main thread; `then` gets [(cmd, ok, detail)]."""
        def go():
            results = run_cmds(cmds)
            if then:
                try:
                    then(results)
                except Exception as exc:
                    sys.stderr.write("[Today] after %s: %r\n" % (cmds[0][0], exc))
        threading.Thread(target=go, daemon=True).start()

    def start_session(self, mode, course_key=None, short=None, note=""):
        if self.session:
            self.end_session(None, quiet=True)          # one at a time; the old one still counts
        now = time.time()
        minutes = quick.MODES[mode]["minutes"]
        self.session = {"mode": mode, "key": course_key, "short": short, "note": note,
                        "started": now, "ends": now + minutes * 60, "minutes": minutes}
        quick.save_session(self.session)

        def started(results):
            title, msg, kind = quick.start_alert(mode, short, minutes, results)
            pomo_alerts.banner(title, msg, note or "", kind)
        self._run_bg(quick.start_cmds(mode, quick.load_registry()), then=started)
        self._show_end(True)
        self.session_timer.start()
        self.tick_session(None)

    def _resume_session(self):
        """Pick up a session the last run of the app left going."""
        s = quick.load_session()
        if not s:
            return
        self.session = s
        if s["ends"] <= time.time():
            self.end_session(None, quiet=True)          # its minutes still count; the alarm is long past
            return
        self._show_end(True)
        self.session_timer.start()
        self.tick_session(None)

    def tick_session(self, _timer):
        s = self.session
        if not s:
            return
        left = s["ends"] - time.time()
        if left <= 0:
            self.end_session(None)
            return
        self.title = quick.countdown_title(s["mode"], s["short"], left)

    def end_session(self, _item, quiet=False):
        s, self.session = self.session, None
        self.session_timer.stop()
        self._show_end(False)
        quick.save_session(None)
        if not s:
            return
        mins = quick.elapsed_minutes(s["started"], time.time(), s["minutes"])
        if mins > 0:
            try:
                apply_ledger(quick.session_op(s["mode"], mins, s["key"], s["note"]))
            except Exception as exc:
                sys.stderr.write("[Today] log session: %r\n" % (exc,))
        self._run_bg(quick.stop_cmds(s["mode"]))
        self.update_title(None)
        if quiet:
            return
        what = quick.label(s["mode"], s["short"])
        msg = "%d min logged. Take a break." % mins if mins else "Nothing logged."
        threading.Thread(target=pomo_alerts.banner,
                         # time running out has to interrupt; ending it herself does not
                         args=("%s done" % what, msg, s["note"] or "",
                               pomo_alerts.SOFT if _item else pomo_alerts.HARD),
                         daemon=True).start()

    def update_title(self, _timer):
        if getattr(self, "session", None):
            return                                      # the countdown owns the title
        state = self._todays_state()
        self.title = format_title(state.get("oneThing", ""), state.get("done", False),
                                  state.get("focus", ""))

    def maybe_notify(self, _timer):
        if getattr(self, "session", None):
            return
        state = self._todays_state()
        one_thing = state.get("oneThing", "")
        done = state.get("done", False)
        focus = state.get("focus", "")
        if should_notify(one_thing, done, focus):
            notify("Still on it?", focus or one_thing)


if __name__ == "__main__":
    _name_status_item()
    TodayApp().run()
