"""Everything that has to be open or true before she can work on a class,
as an ordered list of rows the server runs and the page shows ticking.

The registry only holds overrides; defaults live here so a course with no
`kit` at all still gets notes, focus, and the physical checklist."""
from today_profile import PROFILE, lms_course_url
import os
import subprocess

DEFAULT_NOTES = PROFILE["notesUrl"]
DEFAULT_PHYSICAL = ["pencil + notebook", "water", "phone in the drawer"]
CHROME = "/Applications/Google Chrome.app"
FOCUS_ON = "Study"
FOCUS_OFF = "Study Off"
TIMEOUT = 10


def web_playlist(playlist):
    """Her study playlist is a SoundCloud set. There is no player to script
    (Spotify is gone from the kit at her ask), so it is a tab in her real
    Chrome, like the homework - and only a web URL counts as a playlist."""
    return bool(playlist) and str(playlist).startswith(("http://", "https://"))


def music_cmd(action, playlist):
    """The command for a music action, or None when there is nothing to run:
    play with no web playlist, or pause - a tab can't be paused from here."""
    if action == "play" and web_playlist(playlist):
        return _open([playlist])
    return None


def _browsable(url):
    """A machine export is not a tab: the published-CSV form of a Google Sheet
    downloads a file when opened in Chrome. Open the readable view instead."""
    if not url:
        return None
    return url.replace("/pub?output=csv", "/pubhtml")


def _open(urls):
    """Open tabs in her real Chrome - the signed-in profile.

    `open -a` hands URLs to whichever Chrome process LaunchServices reaches
    first, and there are several: the planner has its own profile, and the
    sync's agent-browser keeps more. Brightspace landing in one of those is
    a login page, not the homework. `-n --args` starts Chrome fresh with the
    default profile; if that profile is already running it takes the URLs
    and the new process exits, so it always ends in the same window.

    Brightspace file names carry spaces; `open` reads those as paths.
    """
    urls = [u.replace(" ", "%20") for u in urls]
    if os.path.isdir(CHROME):
        return ["open", "-na", "Google Chrome", "--args"] + urls
    return ["open"] + urls


def _short_role(link):
    """First clause of the registry's role text, so the kit row stays one line."""
    text = (link.get("role") or link.get("kind") or "link").strip()
    for sep in (";", " - ", ":", ","):
        text = text.split(sep)[0]
    return text.strip()[:28]


MATERIALS_MAX = 4
# The school's learning platform (its sign-in is the one that must not be opened twice at once).
def is_brightspace(url, p=None):
    host = (p or PROFILE)["lms"]["host"]
    return isinstance(url, str) and bool(host) and ("://" + host) in url


def hold_brightspace(rows):
    """One door into Brightspace. Its login (Shibboleth) keeps a single
    sign-in conversation per browser, so several logged-out tabs opened at
    once each start one and only the last survives - every tab she actually
    signs in on lands on the school's "Error / you used the Back button" page.
    The first Brightspace URL opens with the kit; the rest move to `held`
    on their row, for the page to open once she's in."""
    seen_one = False
    for r in rows:
        urls = r.get("urls") or []
        if not urls:
            continue
        keep, held = [], []
        for u in urls:
            if is_brightspace(u) and seen_one:
                held.append(u)
            else:
                keep.append(u)
                if is_brightspace(u):
                    seen_one = True
        if not held:
            continue
        r["held"] = held
        r["cmd"] = _open(keep) if keep else None
        n = len(held)
        r["detail"] = ("%s · " % r["detail"] if r.get("detail") else "") + \
                      "%d on Brightspace open%s when your desk is ready" % (n, "s" if n == 1 else "")
    return rows


def build_rows(course, playlist=None, music_off=False, assignment=None, materials=None):
    """assignment: {title, url} for the specific homework she pressed start on;
    materials: [{title, url}] the weekly slides/notes that go with it. The
    homework opens first, its materials next, the class links last - context
    in the order she needs it."""
    k = course.get("kit") or {}
    rows = []
    if web_playlist(playlist):
        # SoundCloud opens as a tab and waits for her play button - say so
        rows.append({"id": "playlist", "label": "playlist open - press play",
                     "cmd": music_cmd("play", playlist), "skip": bool(music_off)})
    hw_url = (assignment or {}).get("url") if isinstance(assignment, dict) else None
    if hw_url:
        rows.append({"id": "homework", "label": "this homework",
                     "detail": ((assignment.get("title") or "").strip())[:60],
                     "urls": [hw_url], "cmd": _open([hw_url])})
    mat_urls, mat_titles, seen = [], [], set([hw_url]) if hw_url else set()
    for m in (materials if isinstance(materials, list) else []):
        if not isinstance(m, dict) or not m.get("url") or m["url"] in seen:
            continue
        seen.add(m["url"])
        mat_urls.append(m["url"])
        mat_titles.append((m.get("title") or "").strip()[:48])
        if len(mat_urls) >= MATERIALS_MAX:
            break
    if mat_urls:
        rows.append({"id": "materials", "label": "%d material%s" % (len(mat_urls), "" if len(mat_urls) == 1 else "s"),
                     "detail": " · ".join(mat_titles), "urls": mat_urls, "cmd": _open(mat_urls)})
    links = []
    for l in course.get("links") or []:
        url = _browsable(l.get("url"))
        if not url and l.get("kind") in ("brightspace", "canvas") and course.get("brightspaceId"):
            # the registry lists Brightspace by id, not url; its Content page is the tab
            url = lms_course_url(PROFILE, course["brightspaceId"])
            l = dict(l, role=l.get("role") or l.get("kind"))
        if not url or url in seen or str(l.get("access") or "").upper().startswith("LOCK"):
            continue
        links.append(dict(l, url=url))
    if links:
        rows.append({"id": "tabs",
                     "label": "%d tab%s" % (len(links), "" if len(links) == 1 else "s"),
                     "detail": " · ".join(_short_role(l) for l in links),
                     "urls": [l["url"] for l in links],
                     "cmd": _open(l["url"] for l in links)})
    notes = k.get("notes") or DEFAULT_NOTES
    rows.append({"id": "notes", "label": "notes", "cmd": _open([notes])})
    for app in k.get("apps") or []:
        rows.append({"id": "app:%s" % app, "label": app, "cmd": ["open", "-a", app]})
    rows.append({"id": "focus", "label": "focus on", "cmd": ["shortcuts", "run", FOCUS_ON]})
    rows.append({"id": "physical", "label": "physical", "cmd": None,
                 "items": list(k.get("physical") or DEFAULT_PHYSICAL)})
    hold_brightspace(rows)
    for r in rows:
        r.setdefault("ok", None)
        r.setdefault("detail", "")
    return rows


def _run_one(cmd, runner):
    try:
        p = runner(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "timed out after %ss" % TIMEOUT
    except FileNotFoundError:
        return False, "missing: %s" % cmd[0]
    except Exception as exc:                      # anything else the runner throws
        return False, str(exc)[:120]
    if p.returncode == 0:
        return True, ""
    err = (getattr(p, "stderr", "") or "").strip().splitlines()
    return False, (err[0] if err else "exit %s" % p.returncode)[:120]


def run_rows(rows, runner=subprocess.run):
    for r in rows:
        if r.get("cmd") is None:
            continue
        if r.get("skip"):
            r["ok"], r["detail"] = None, "off for today"
            continue
        ok, detail = _run_one(r["cmd"], runner)
        if not ok and r["id"] == "focus":
            detail = "make a Shortcut called %s" % FOCUS_ON
        r["ok"] = ok
        r["detail"] = detail if not ok else r.get("detail", "")
    return rows


def stop_cmds():
    return [["shortcuts", "run", FOCUS_OFF]]


def run_stop(runner=subprocess.run):
    return [dict(zip(("ok", "detail"), _run_one(c, runner))) for c in stop_cmds()]


def run_music(action, playlist, runner=subprocess.run):
    if action == "pause":                            # the SoundCloud tab is hers to pause; nothing to run
        return {"ok": True, "detail": ""}
    cmd = music_cmd(action, playlist)
    if cmd is None:
        return {"ok": False, "detail": "no web studyPlaylist in ~/.courses.json" if action == "play"
                else "unknown action %s" % action}
    ok, detail = _run_one(cmd, runner)
    return {"ok": ok, "detail": detail}
