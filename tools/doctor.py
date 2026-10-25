#!/usr/bin/env python3
"""Is Today set up right on this Mac? Plain lines, problems first.

    python3 tools/doctor.py          settings, tools, background jobs, last sync
    python3 tools/doctor.py --live   also ask the school platform whether the sign-in still works

Exit 1 when something blocks Today from working; notes alone exit 0.
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.expanduser(os.environ.get("TODAY_PROFILE", "~/.today/profile.json"))
CACHE = os.path.expanduser("~/.study-cache.json")
LMS_KINDS = ("brightspace", "canvas")


def load_json(path):
    try:
        with open(os.path.expanduser(path)) as fh:
            return json.load(fh), None
    except OSError:
        return None, "missing"
    except ValueError as e:
        return None, "not valid JSON (%s)" % e


def check_settings(profile, courses):
    """(problems, notes) for a profile dict and a courses dict. Pure, so tests can feed it examples."""
    problems, notes = [], []
    lms = profile.get("lms") or {}
    kind, host = lms.get("kind") or "", lms.get("host") or ""
    if kind in LMS_KINDS and not host:
        problems.append("profile lms.kind is %s but lms.host is empty (e.g. %s.yourschool.edu)" % (kind, kind))
    if host.startswith("http"):
        problems.append("profile lms.host should be just the address, without https://")
    if not profile.get("name") or profile.get("name") == "you":
        notes.append("profile has no name; the planner will call you \"you\"")

    items = courses.get("courses")
    if not isinstance(items, list) or not items:
        problems.append("courses.json has no \"courses\" list")
        return problems, notes
    keys = [c.get("key") for c in items]
    for i, c in enumerate(items):
        label = c.get("key") or "course #%d" % (i + 1)
        if not c.get("key") or not c.get("name"):
            problems.append("%s needs both key and name" % label)
        elif any(ch.isspace() or ch.isupper() for ch in c["key"]):
            problems.append("%s: key should be lowercase with no spaces" % label)
        meets = c.get("meets") or {}
        for t in ("start", "end"):
            v = meets.get(t)
            if v and not (len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit()):
                problems.append("%s: meets.%s should look like 14:30" % (label, t))
        on_lms = any((s or {}).get("kind") in LMS_KINDS for s in c.get("sources") or [])
        if on_lms and not (c.get("lmsId") or c.get("brightspaceId")):
            notes.append("%s links the school platform but has no lmsId, so its platform deadlines won't attach" % label)
        weights = (c.get("gradeScheme") or {}).get("weights") or c.get("grading")
        if isinstance(weights, dict) and weights:
            total = sum(v for v in weights.values() if isinstance(v, (int, float)))
            if abs(total - 1) > 0.02:
                notes.append("%s: grade weights add to %.2f, not 1" % (label, total))
    dupes = sorted({k for k in keys if k and keys.count(k) > 1})
    if dupes:
        problems.append("duplicate course keys: %s" % ", ".join(dupes))
    for k in (profile.get("quizPrep") or {}).get("courses") or []:
        if k not in keys:
            problems.append("quizPrep.courses names %s, which is not a course key" % k)
    return problems, notes


def find_claude():
    for p in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude"),
              os.path.expanduser("~/.claude/local/claude"), "/opt/homebrew/bin/claude"):
        if p and os.path.exists(p):
            return p
    return None


def check_tools(profile):
    problems, notes = [], []
    if not find_claude():
        notes.append("no claude command: briefs, Ask and Quiz Prep's AI need Claude Code")
    if not shutil.which("node"):
        notes.append("no Node.js: Quiz Prep stays off")
    kind = (profile.get("lms") or {}).get("kind")
    if kind == "brightspace" and not (shutil.which("agent-browser") or os.path.exists(os.path.expanduser("~/.local/bin/agent-browser"))):
        problems.append("Brightspace needs agent-browser: npm install -g agent-browser && agent-browser install")
    if kind == "canvas" and not (os.environ.get("CANVAS_TOKEN") or os.path.exists(os.path.expanduser("~/.today/canvas-token"))):
        problems.append("no Canvas token yet: run connectors/canvas/canvas login")
    return problems, notes


def check_live(profile):
    kind = (profile.get("lms") or {}).get("kind")
    cli = {"brightspace": os.path.join(ROOT, "connectors", "brightspace", "bs"),
           "canvas": os.path.join(ROOT, "connectors", "canvas", "canvas")}.get(kind)
    if not cli or not (profile.get("lms") or {}).get("host"):
        return [], []
    p = subprocess.run([sys.executable, cli, "status"], capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        return ["%s sign-in is not working: run %s login" % (kind, os.path.relpath(cli, ROOT))], []
    return [], ["%s sign-in works" % kind]


def check_jobs(profile):
    label = profile.get("launchLabel") or "today.planner"
    notes = []
    for l in (label, profile.get("syncLabel") or label + ".sync"):
        p = subprocess.run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), l)], capture_output=True, text=True)
        if p.returncode != 0:
            notes.append("background job %s is not installed (tools/install.sh --yes)" % l)
    return [], notes


def check_sync(cache_path=CACHE, now=None):
    data, err = load_json(cache_path)
    if err:
        return [], ["no course sync yet (it runs during install, then every 2 hours)"]
    notes = []
    age_h = ((now or time.time()) - os.path.getmtime(os.path.expanduser(cache_path))) / 3600
    if age_h > 6:
        notes.append("last course sync was %d hours ago" % age_h)
    for e in (data.get("errors") or [])[:6]:
        notes.append("sync said: %s: %s" % (e.get("source"), str(e.get("error"))[:140]))
    return [], notes


def main(argv):
    profile, perr = load_json(PROFILE)
    if perr:
        print("!! profile %s is %s. Do the setup interview (CLAUDE-SETUP.md)." % (PROFILE, perr))
        return 1
    courses_path = profile.get("coursesPath") or "~/.courses.json"
    courses, cerr = load_json(courses_path)
    if cerr:
        print("!! course list %s is %s." % (courses_path, cerr))
        return 1
    problems, notes = check_settings(profile, courses)
    for check in (check_tools, check_jobs):
        p, n = check(profile)
        problems += p
        notes += n
    p, n = check_sync()
    problems += p
    notes += n
    if "--live" in argv:
        p, n = check_live(profile)
        problems += p
        notes += n
    for line in problems:
        print("!! " + line)
    for line in notes:
        print("-  " + line)
    if not problems:
        print("ok: %d classes, platform %s" % (len(courses.get("courses") or []),
                                               (profile.get("lms") or {}).get("kind") or "none"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
