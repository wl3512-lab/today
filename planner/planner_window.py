"""The planner in a window of its own, instead of a second Google Chrome.

It used to open as a Chrome --app window in a separate profile. macOS knows
that process only as "Google Chrome", so whenever her real Chrome was closed,
clicking Chrome in the Dock activated the planner's windowless instance and
nothing appeared, and links clicked in other apps landed in it
(planner_guard.py closed them again and forwarded them). Here the page runs in
WebKit inside the menubar app itself. macOS sees a different app, so Chrome
in the Dock and every link always mean her real Chrome.

Links the page opens (window.open, link clicks to the web) go to her default
browser. The page's data is unchanged: state.json through the server on 8765,
plus localStorage, which this window keeps in its own WebKit store. The first
time it opens, the localStorage saved from the old Chrome profile
(.chrome-localstorage.json) is copied in before the page's own scripts run.

To go back to the Chrome window: touch ~/today-planner/.planner-in-chrome
"""
import json
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_OUT_FILE = os.path.join(APP_DIR, ".planner-in-chrome")
MIGRATION_FILE = os.path.join(APP_DIR, ".chrome-localstorage.json")
IMPORTED_FILE = os.path.join(APP_DIR, ".chrome-localstorage.imported.json")
MIGRATED_FLAG = "today.migratedFromChrome"
AUTOSAVE_NAME = "TodayPlannerWindow"

try:
    import objc
    from AppKit import (NSApp, NSApplication, NSBackingStoreBuffered, NSMakeRect, NSMenu,
                        NSMenuItem, NSWindow, NSWorkspace, NSViewHeightSizable,
                        NSViewWidthSizable, NSWindowStyleMaskClosable,
                        NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
                        NSWindowStyleMaskTitled)
    from Foundation import NSObject, NSThread, NSURL
    from WebKit import (WKNavigationActionPolicyAllow, WKNavigationActionPolicyCancel,
                        WKUserScript, WKUserScriptInjectionTimeAtDocumentStart, WKWebView,
                        WKWebViewConfiguration)
    AVAILABLE = True
except Exception as exc:                      # no PyObjC WebKit: the Chrome window stays
    sys.stderr.write("[Today] native planner window unavailable: %r\n" % (exc,))
    AVAILABLE = False


def read_root(path, repo=None):
    """The folder the page may read files from.

    WebKit only loads file:// URLs under the folder it is given; Chrome loaded
    anything. The Internships page and the résumé chat come from the internship
    agent's clone beside the planner (../internship-agent/ui/), so a root of
    just ~/today-planner silently blocked them and the Internships page never
    loaded. The root is the common parent of the planner and the clone.
    """
    dirs = [os.path.dirname(os.path.abspath(path))]
    if repo is None:
        # plugins may bring page files from elsewhere (the internship agent's clone, for one)
        try:
            import plugins
            from today_profile import PROFILE
            plugins.load(plugins.names_for(PROFILE))
            extra = plugins.read_roots()
        except Exception:
            extra = []
    else:
        extra = [repo]
    dirs += [os.path.abspath(r) for r in extra if r and os.path.isdir(r)]
    return os.path.commonpath(dirs)


def wanted(app_dir=APP_DIR):
    """Use the native window unless she has asked for the Chrome one back."""
    return AVAILABLE and not os.path.exists(os.path.join(app_dir, os.path.basename(OPT_OUT_FILE)))


def goes_to_browser(url, main_frame=True):
    """Does a navigation leave the planner for her real browser?

    The planner and its local pages are file:// and stay. Anything on the web,
    mailto: and the like go out. Frames inside the page are the page's own
    business and stay too.
    """
    if not main_frame:
        return False
    scheme = (url or "").split(":", 1)[0].lower()
    return scheme not in ("file", "about", "blob", "data", "")


def migration_script(entries, flag=MIGRATED_FLAG):
    """JS that copies the old Chrome localStorage in, once, before the page runs.

    Guarded by a flag key, so a second load (or a second launch) never writes
    old values over newer ones.
    """
    return ("(function(){try{if(localStorage.getItem(%s))return;var d=%s;"
            "for(var k in d){if(Object.prototype.hasOwnProperty.call(d,k))"
            "localStorage.setItem(k,d[k]);}"
            "localStorage.setItem(%s,new Date().toISOString());}catch(e){}})();"
            % (json.dumps(flag), json.dumps(entries), json.dumps(flag)))


def load_migration(path=MIGRATION_FILE):
    try:
        with open(path) as fh:
            data = json.load(fh)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


if AVAILABLE:
    # No protocols=[...] here, on purpose. Declaring WKNavigationDelegate makes
    # PyObjC take each method's type from the protocol, which describes the
    # decisionHandler only as "a block" - and calling a block it cannot describe
    # raises inside WebKit's callback and takes the whole menubar app down. Left
    # undeclared, PyObjC uses the WebKit bindings' own metadata, which has the
    # block's full signature (the same way pywebview does it).
    class _Delegate(NSObject):
        def initWithOwner_(self, owner):
            self = objc.super(_Delegate, self).init()
            if self is not None:
                self.owner = owner
            return self

        # links, form posts, location changes
        def webView_decidePolicyForNavigationAction_decisionHandler_(self, web, action, handler):
            policy = WKNavigationActionPolicyAllow
            try:
                url = action.request().URL()
                frame = action.targetFrame()
                main = frame is None or frame.isMainFrame()
                if url is not None and goes_to_browser(str(url.absoluteString()), main):
                    NSWorkspace.sharedWorkspace().openURL_(url)
                    policy = WKNavigationActionPolicyCancel
            except Exception as exc:          # an exception here would crash the menubar
                sys.stderr.write("[Today] planner window navigation: %r\n" % (exc,))
            handler(policy)

        # window.open(url, "_blank") and target=_blank: her browser, never a new planner
        def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
                self, web, config, action, features):
            url = action.request().URL()
            if url is not None and str(url.absoluteString()):
                NSWorkspace.sharedWorkspace().openURL_(url)
            return None

        def webView_didFinishNavigation_(self, web, nav):
            self.owner._loaded(web)

        def windowWillClose_(self, note):
            self.owner._closed()


class PlannerWindow:
    """One planner window. Opening it again brings it forward."""

    def __init__(self):
        self.window = None
        self.web = None
        self.delegate = None
        self.loaded_mtime = None
        self.path = None

    def show(self, path):
        if not NSThread.isMainThread():
            from PyObjCTools import AppHelper
            AppHelper.callAfter(self.show, path)
            return
        if self.window is None:
            self._make(path)
        elif self.path != path or self._mtime(path) != self.loaded_mtime:
            self._load(path)                     # the planner file changed: show the new one
        NSApp.activateIgnoringOtherApps_(True)
        if self.window.isMiniaturized():
            self.window.deminiaturize_(None)
        self.window.makeKeyAndOrderFront_(None)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    def _make(self, path):
        _ensure_edit_menu()
        config = WKWebViewConfiguration.alloc().init()
        try:
            config.preferences().setValue_forKey_(True, "developerExtrasEnabled")
        except Exception:
            pass
        entries = load_migration()
        if entries:
            script = WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                migration_script(entries), WKUserScriptInjectionTimeAtDocumentStart, True)
            config.userContentController().addUserScript_(script)
        self.delegate = _Delegate.alloc().initWithOwner_(self)
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 1280, 860), style, NSBackingStoreBuffered, False)
        win.setTitle_("Today")
        win.setReleasedWhenClosed_(False)
        win.setMinSize_((720, 520))
        win.center()
        win.setFrameAutosaveName_(AUTOSAVE_NAME)    # remembers where she put it
        win.setDelegate_(self.delegate)
        web = WKWebView.alloc().initWithFrame_configuration_(win.contentView().bounds(), config)
        web.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        web.setNavigationDelegate_(self.delegate)
        web.setUIDelegate_(self.delegate)
        win.contentView().addSubview_(web)
        self.window, self.web = win, web
        self._load(path)

    def _load(self, path):
        self.path = path
        self.loaded_mtime = self._mtime(path)
        url = NSURL.fileURLWithPath_(path)
        self.web.loadFileURL_allowingReadAccessToURL_(url, NSURL.fileURLWithPath_(read_root(path)))

    def _loaded(self, web):
        # Count what the page has, so the log shows whether storage carried over.
        def report(result, error):
            # A JSON string, not an object: WebKit hands objects back as an
            # NSDictionary, which is not a Python dict.
            try:
                info = json.loads(str(result)) if result is not None else {}
            except ValueError:
                info = {}
            sys.stderr.write("[Today] planner window loaded: %s localStorage keys, migrated=%s, "
                             "reads %s%s\n"
                             % (info.get("n"), info.get("m"), read_root(self.path or ""),
                                (" (error %r)" % (error,)) if error is not None else ""))
            if info.get("m") and os.path.exists(MIGRATION_FILE):
                try:
                    os.replace(MIGRATION_FILE, IMPORTED_FILE)   # kept as a backup, never re-injected
                except OSError:
                    pass
        web.evaluateJavaScript_completionHandler_(
            "JSON.stringify({n: localStorage.length, m: !!localStorage.getItem(%s)})"
            % json.dumps(MIGRATED_FLAG), report)

    def _closed(self):
        # Closing the window closes the planner, as closing the Chrome window did.
        if self.web is not None:
            self.web.stopLoading()
            self.web.removeFromSuperview()
        self.window, self.web, self.delegate = None, None, None


def _ensure_edit_menu():
    """Copy, paste, undo and select-all need menu items to reach a web view.

    The menubar app has no main menu of its own, and without these the
    shortcuts do nothing in the planner's text fields.
    """
    app = NSApplication.sharedApplication()
    main = app.mainMenu()
    if main is not None and main.itemWithTitle_("Edit") is not None:
        return
    if main is None:
        main = NSMenu.alloc().initWithTitle_("Main")
        app_item = NSMenuItem.alloc().init()
        main.addItem_(app_item)
        app_menu = NSMenu.alloc().initWithTitle_("Today")
        app_item.setSubmenu_(app_menu)
    edit_item = NSMenuItem.alloc().init()
    main.addItem_(edit_item)
    edit = NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in (("Undo", "undo:", "z"), ("Redo", "redo:", "Z"), (None, None, None),
                               ("Cut", "cut:", "x"), ("Copy", "copy:", "c"),
                               ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")):
        if title is None:
            edit.addItem_(NSMenuItem.separatorItem())
        else:
            edit.addItemWithTitle_action_keyEquivalent_(title, action, key)
    edit_item.setSubmenu_(edit)
    win_item = NSMenuItem.alloc().init()
    main.addItem_(win_item)
    win_menu = NSMenu.alloc().initWithTitle_("Window")
    win_menu.addItemWithTitle_action_keyEquivalent_("Minimize", "performMiniaturize:", "m")
    win_menu.addItemWithTitle_action_keyEquivalent_("Close", "performClose:", "w")
    win_menu.addItemWithTitle_action_keyEquivalent_("Reload", "reload:", "r")
    win_item.setSubmenu_(win_menu)
    app.setMainMenu_(main)


WINDOW = PlannerWindow()


def show(path):
    WINDOW.show(path)
