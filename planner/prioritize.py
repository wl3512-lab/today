#!/usr/bin/env python3
"""Score every deadline for stakes, effort, and how far ahead to start.

A due date only says when something is over. For anything bigger than a
reading response that is the wrong question - what matters is when to START,
and which three of forty-one items actually move the grade.

Two layers, deliberately. The rules below always run: free, instant, offline
and explainable, which matters more than cleverness for something that has to
be trusted on a bad-attention day. An optional `claude -p` pass then enriches
only the items the rules call heavy or cannot classify, cached per assignment
for good. If that pass is unavailable the rules stand on their own - nothing
in the planner ever waits on it or breaks without it.
"""

from today_profile import PROFILE
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import ledger

NOTES = os.path.expanduser("~/.assignment-notes.json")

# Ordered: the FIRST match wins, so the specific sits above the general.
# "Project 3 (Midterm) - Research & Concept Post" is a scaffold, not a project,
# and must be read that way or its real job - unblocking the midterm - is lost.
KINDS = [
    ("final",      r"\bfinal\b",                                                     14, 21, 50),
    ("scaffold",   r"concept|research|proposal|wireframe|sitemap|starting prompt"
                   r"|outline|blog setup|storyboard|pitch",                           3,  7, 15),
    ("project",    r"\bproject\b|case study|\bpaper\b|presentation|\bmidterm\b",      9, 12, 50),
    ("problemset", r"homework|problem set|\bhw\b|\bpset\b",                           3,  4, 20),
    ("exam",       r"\bexam\b",                                                       6, 10, 40),
    ("quiz",       r"\bquiz\b",                                                       2,  4, 10),
    ("response",   r"^response\b|reading response|response #|reflection|one-minute", 2.5,  3, 10),
    ("discussion", r"post here|discussion|respond to|blog post",                      1,  2, 10),
    ("admin",      r"survey|required course tools|introduction|setup|sign[- ]up"
                   r"|evaluation|attendance",                                         1,  1,  5),
]

BANDS = ("low", "medium", "high")

# Work that does not have to be done at all must never outrank work that does.
# "Extra Credit Paper" matched `paper` and came back high, ranked beside a
# midterm - which is the planner arguing for the one thing she could skip.
OPTIONAL = re.compile(r"(?i)\bextra credit\b|\boptional\b|\bbonus\b|\bungraded\b")


def now_utc():
    return datetime.now(timezone.utc)


def parse_dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def item_id(course_key, d):
    """Stable per assignment, so an AI note written once is never re-bought."""
    raw = "%s|%s|%s" % (course_key, (d.get("title") or "").strip(), d.get("due") or "")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def points(title):
    m = re.search(r"\((\d{1,3})\s*(?:pts?|points?)\)", title or "", re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d{1,3})\s*(?:pts|points)\b", title or "", re.I)
    return int(m.group(1)) if m else None


def parts(title):
    """How many things this actually is.

    "Blog setup + reflection + experiments" is one row and three evenings, and
    "post, then respond to 2 classmates" is the assignment people half-finish.
    """
    t = (title or "").lower()
    n = 1 + t.count("+")
    # "both due" usually just restates the "+" that is already counted; only a
    # second action verb genuinely adds a part.
    if re.search(r"then respond|and respond|respond to the posts", t):
        n += 1
    elif n == 1 and "both due" in t:
        n += 1
    return min(n, 4)


def classify(title):
    t = (title or "").lower()
    for name, pat, hours, lead, default_pts in KINDS:
        if re.search(pat, t):
            return name, hours, lead, default_pts
    return "task", 3, 4, 15


# Project 5's wireframes and Project 5's final are the same body of work split
# across two dates. Miss the first and the second is already in trouble, so the
# early stage has to be read as a gate rather than as a small standalone task.
STAGE = re.compile(r"\b(project|assignment|homework|hw|paper|unit)\s*#?\s*(\d+)", re.I)


def stage_key(title):
    m = STAGE.search(title or "")
    return "%s-%s" % (m.group(1).lower(), m.group(2)) if m else None


def band_for(hours, stakes, flags, title):
    """The same thresholds everywhere: at scoring time on the estimate, and
    again after the ledger has been subtracted from it."""
    if OPTIONAL.search(title or ""):
        return "low"
    if hours >= 6 or stakes >= 40:
        return "high"
    if hours >= 2.5 or stakes >= 15 or "gate" in (flags or []):
        return "medium"
    return "low"


def score_course(course, ref=None):
    """Attach a `priority` block to every deadline in one course."""
    ref = ref or now_utc()
    dls = course.get("deadlines") or []

    groups = {}
    for d in dls:
        k = stage_key(d.get("title"))
        if k:
            groups.setdefault(k, []).append(d)

    for d in dls:
        title = d.get("title") or ""
        due = parse_dt(d.get("due"))
        kind, base_h, base_lead, default_pts = classify(title)
        n_parts = parts(title)

        hours = round(base_h * (1 + 0.45 * (n_parts - 1)), 1)
        # An instructor writing "budget 6 to 9 hours" in the assignment beats
        # anything inferable from its title, and beats the model too.
        hint = d.get("hoursHint")
        authoritative = bool(hint)
        if authoritative:
            hours = float(hint)
        # Three weeks is the most notice any of this deserves; past that the
        # warning is just noise she learns to scroll past.
        lead = min(21, int(round(base_lead * (1 + 0.25 * (n_parts - 1)))))
        if authoritative:
            lead = min(21, max(lead, int(round(hours * 1.3))))
        pts = points(title)
        stakes = pts if pts is not None else default_pts

        why, flags = [], []
        started = d.get("mine")
        if started:
            flags.append("started")
            why.append("underway - %d file%s pushed to your repo" % (
                started.get("files", 0), "" if started.get("files") == 1 else "s"))
        if authoritative:
            why.append("instructor budgets ~%gh" % hours)
        if pts is not None:
            why.append("%d pts" % pts)
        if n_parts > 1:
            why.append("%d separate parts" % n_parts)
            flags.append("multipart")

        # gate: an early stage that a later, bigger one is built on
        k = stage_key(title)
        siblings = sorted([s for s in groups.get(k, []) if parse_dt(s.get("due"))],
                          key=lambda s: s["due"]) if k else []
        if len(siblings) > 1 and due and siblings[-1] is not d:
            later = siblings[-1]
            flags.append("gate")
            why.append("feeds “%s”" % (later.get("title") or "")[:40].strip())
            lead = max(lead, 5)

        if OPTIONAL.search(title):
            flags.append("optional")
            why.append("optional")
        band = band_for(hours, stakes, flags, title)

        start_by = due - timedelta(days=lead) if due else None
        if start_by and due:
            if start_by <= ref:
                flags.append("start-now")
                # Do not tell her to start something she has already started.
                # The repo says five files are in; "should already be underway"
                # next to that reads as a planner that is not paying attention.
                if "started" not in flags:
                    why.insert(0, "should already be underway" if band == "high"
                               else "start it this week")
            elif (start_by - ref).days <= 3:
                flags.append("start-soon")

        d["priority"] = {
            "id": item_id(course.get("key", ""), d),
            "kind": kind,
            "band": band,
            "hours": hours,
            "leadDays": lead,
            "startBy": iso(start_by) if start_by else None,
            "stakes": stakes,
            "estimated": pts is None,
            "flags": flags,
            "why": why,
            "hoursFixed": authoritative,
            "source": "instructor" if authoritative else "rules",
        }
    return dls


def mark_collisions(courses, window_days=3):
    """Two heavy things landing in the same few days is its own problem."""
    heavy = []
    for c in courses:
        for d in c.get("deadlines") or []:
            p = d.get("priority") or {}
            due = parse_dt(d.get("due"))
            if p.get("band") == "high" and due:
                heavy.append((due, c.get("short") or c.get("name"), d))
    for due, short, d in heavy:
        clash = [o_short for o_due, o_short, o in heavy
                 if o is not d and abs((o_due - due).days) <= window_days]
        if clash:
            p = d["priority"]
            p["flags"].append("collision")
            p["why"].append("lands with %s" % ", ".join(sorted(set(clash))[:2]))


def focus(courses, ref=None, limit=6):
    """What deserves thought now, regardless of which class it belongs to."""
    ref = ref or now_utc()
    out = []
    for c in courses:
        for d in c.get("deadlines") or []:
            p = d.get("priority") or {}
            due, start = parse_dt(d.get("due")), parse_dt(p.get("startBy"))
            if not due or due < ref or not start:
                continue
            if start > ref + timedelta(days=3):
                continue          # not yet worth the working memory
            out.append({
                "optional": "optional" in (p.get("flags") or []),
                "course": c.get("short") or c.get("name"), "key": c.get("key"),
                "title": d.get("title"), "due": d.get("due"), "url": d.get("url", ""),
                "band": p.get("band"), "hours": p.get("hours"),
                "logged": p.get("logged", 0), "remaining": p.get("remaining"), "id": p.get("id"),
                "startBy": p.get("startBy"), "why": p.get("why", []),
                "flags": p.get("flags", []), "firstStep": p.get("firstStep"),
            })
    rank = {"high": 0, "medium": 1, "low": 2}
    # Optional work sinks below everything required, whatever its due date.
    out.sort(key=lambda x: (bool(x["optional"]), rank.get(x["band"], 3), x["due"]))
    return out[:limit]


# --------------------------------------------------------------------------
# optional AI layer
# --------------------------------------------------------------------------

def load_notes():
    try:
        with open(NOTES) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (IOError, ValueError):
        return {}


def save_notes(notes):
    tmp = NOTES + ".tmp"
    with open(tmp, "w") as f:
        json.dump(notes, f, indent=2)
    os.replace(tmp, NOTES)


PROMPT = """You are helping {learner} triage coursework. For each \
assignment below, judge how much real work it is and what makes it hard to \
start. Be concrete and blunt; do not pad.

Return ONLY a JSON array, one object per assignment, no prose, no code fence:
[{"id":"<id>","hours":<realistic solo hours, number>,\
"why":"<max 12 words: what actually makes this heavy>",\
"firstStep":"<max 12 words: a first action doable in 15 minutes>"}]

Assignments:
%s
"""
PROMPT = PROMPT.replace("{learner}", PROFILE["learner"])   # profile["learner"], e.g. "a student"


def parse_rows(raw):
    """Pull the JSON array out of a reply, or None if there isn't one.

    Scans for a bracket-balanced span rather than taking everything between the
    first "[" and the last "]": prose that happens to contain a bracket made
    the greedy version swallow the lot and silently return nothing.
    """
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    for start in (i for i, ch in enumerate(raw) if ch == "["):
        depth, in_str, esc = 0, False, False
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        rows = json.loads(raw[start:i + 1])
                    except ValueError:
                        break
                    if isinstance(rows, list):
                        return rows
                    break
    return None


def claude_bin():
    """Absolute path to the claude CLI, or None.

    Same lesson as agent-browser: a bare name resolves in a terminal and
    vanishes under a scheduler with a minimal PATH, and the failure is silent
    here by design - so it would have looked like the model simply had nothing
    to say, forever.
    """
    found = shutil.which("claude")
    if found:
        return found
    for cand in ("~/.local/bin/claude", "/opt/homebrew/bin/claude",
                 "/usr/local/bin/claude"):
        cand = os.path.expanduser(cand)
        if os.access(cand, os.X_OK):
            return cand
    return None


def ask_claude(pending, timeout=240):
    """One batched call. Any failure returns {} and the rules stand alone."""
    exe = claude_bin()
    if not exe:
        return {}
    lines = []
    for it in pending:
        desc = (it.get("body") or "").strip().replace("\n", " ")[:400]
        lines.append("- id=%s | course=%s | due=%s | %s%s" % (
            it["id"], it["course"], (it.get("due") or "")[:10], it["title"],
            ("  || description: " + desc) if desc else ""))
    try:
        # Run somewhere with no project of its own. Invoked inside the planner
        # repo it inherits that project's CLAUDE.md and settings, and starts
        # answering as an assistant working on this codebase - one batch came
        # back as prose about `ask_claude` itself instead of the JSON asked
        # for. A neutral cwd keeps it a classifier.
        with tempfile.TemporaryDirectory() as neutral:
            p = subprocess.run(
                [exe, "-p", PROMPT % "\n".join(lines), "--output-format", "text"],
                capture_output=True, text=True, timeout=timeout, cwd=neutral)
    except Exception:
        return {}
    if p.returncode != 0:
        return {}
    rows = parse_rows((p.stdout or "").strip())
    if rows is None:
        return {}
    out = {}
    for r in rows if isinstance(rows, list) else []:
        rid = str(r.get("id") or "")
        if not rid:
            continue
        try:
            hours = float(r.get("hours"))
        except (TypeError, ValueError):
            hours = None
        out[rid] = {"hours": hours,
                    "why": str(r.get("why") or "")[:90],
                    "firstStep": str(r.get("firstStep") or "")[:90]}
    return out


def enrich(courses, bodies=None, budget=14, enabled=True):
    """Ask the model about the heavy and the unclassifiable, once each, ever.

    Deliberately narrow: a reading response worth 10 points does not need a
    language model to explain it, and paying for that every two hours would be
    the kind of quiet waste nobody notices for months.
    """
    notes = load_notes()
    bodies = bodies or {}
    pending, index = [], {}

    for c in courses:
        for d in c.get("deadlines") or []:
            p = d.get("priority") or {}
            pid = p.get("id")
            if not pid:
                continue
            index[pid] = d
            if pid in notes:
                continue
            if (p.get("band") == "high" or p.get("kind") == "task"
                    or p.get("hours", 0) >= 4 or "gate" in p.get("flags", [])):
                pending.append({"id": pid, "title": d.get("title"),
                                "course": c.get("short") or c.get("name"),
                                "due": d.get("due"),
                                # A deadline that carries its own text - parsed
                                # weekly homework does - is far better evidence
                                # than a title, so prefer it.
                                "body": d.get("body") or bodies.get(d.get("title"))})

    if enabled and pending:
        fresh = ask_claude(pending[:budget])
        for pid, note in fresh.items():
            notes[pid] = note
        if fresh:
            save_notes(notes)

    applied = 0
    ref = now_utc()
    for pid, note in notes.items():
        d = index.get(pid)
        if not d:
            continue
        p = d["priority"]
        if note.get("hours") and not p.get("hoursFixed"):
            # Trust the model on scale, but never let it argue a 50-point
            # project down into something that needs no lead time.
            p["hours"] = max(p["hours"], round(float(note["hours"]), 1)) \
                if p["band"] == "high" else round(float(note["hours"]), 1)
        if note.get("why"):
            p["why"].append(note["why"])
        if note.get("firstStep"):
            p["firstStep"] = note["firstStep"]
        # A revised estimate is worthless if the date to start on stays where
        # the rules put it: the model saying "12 hours, cramming fails" has to
        # move the start line, not just the label.
        due = parse_dt(d.get("due"))
        lead = min(21, max(p["leadDays"], int(round(p["hours"] * 1.3))))
        p["leadDays"] = lead
        if due:
            start = due - timedelta(days=lead)
            p["startBy"] = iso(start)
            p["flags"] = [f for f in p["flags"] if f not in ("start-now", "start-soon")]
            if start <= ref:
                p["flags"].append("start-now")
            elif (start - ref).days <= 3:
                p["flags"].append("start-soon")
        p["source"] = "instructor+ai" if p.get("hoursFixed") else "rules+ai"
        applied += 1
    return applied, len(pending)


def apply(feed, bodies=None, ai=True, ledger_path=None):
    ref = now_utc()
    for c in feed.get("courses", []):
        score_course(c, ref)
    enrich(feed.get("courses", []), bodies=bodies, enabled=ai)
    subtract_logged(feed, ledger_path or ledger.LEDGER)
    mark_collisions(feed.get("courses", []))
    feed["focus"] = focus(feed.get("courses", []), ref)
    return feed


def subtract_logged(feed, ledger_path):
    """Hours she has actually put in come off the estimate. `hours` itself is
    left alone so the bar's denominator never moves under her. Stakes shrink
    with the work left too: a final project with one hour to go should not
    keep shouting like an untouched one. Flags like gate are not scaled -
    they describe structure, not effort - but once nothing is left the band
    is low whatever the flags say."""
    by_dl, _by_course = ledger.logged_hours(ledger.load(ledger_path))
    for c in feed.get("courses", []):
        for d in c.get("deadlines") or []:
            p = d.get("priority")
            if not p:
                continue
            hours = p.get("hours") or 0
            logged = round(by_dl.get(p.get("id"), 0), 2)
            remaining = max(0.0, round(hours - logged, 2))
            frac = (remaining / hours) if hours else 1.0
            p["logged"] = logged
            p["remaining"] = remaining
            if remaining <= 0:
                p["band"] = "low"
            else:
                p["band"] = band_for(remaining, round((p.get("stakes") or 0) * frac, 1),
                                     p.get("flags", []), d.get("title"))
