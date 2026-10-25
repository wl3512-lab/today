#!/usr/bin/env python3
"""Merge every course source into one cache the planner can read.

Five classes publish through six systems - Brightspace, GitHub, published
Google Docs/Sheets, Campuswire, Gradescope - and no two the same way. This
flattens all of it into ~/.study-cache.json.

Doctrine: every source is optional. One failing source degrades to a note in
`errors` and never removes the others; a planner that loses a class because a
network call failed is worse than one that shows nothing.
"""

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import prioritize
import plugins
from today_profile import PROFILE
import calendar_feed
import discord_digest
import grades
import briefs

REGISTRY = os.path.expanduser(PROFILE["coursesPath"])

# One hue per class, so a row can be placed without reading it. Assigned from
# registry order rather than hashed or positional, because the course list
# re-sorts by urgency every sync and a colour that moves teaches nothing.
# Deliberately steers clear of ~22 (slip) and ~155 (kept): those two angles
# already mean something in this product and must not also mean a class.
HUES = [265, 335, 205, 80, 300, 240, 175, 20]
CACHE = os.path.expanduser("~/.study-cache.json")
CONNECTORS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "connectors")


def connector(name, script):
    """The CLI shipped in ../connectors, else one installed as a Claude skill."""
    shipped = os.path.join(CONNECTORS, name, script)
    return shipped if os.path.exists(shipped) else os.path.expanduser("~/.claude/skills/%s/%s" % (name, script))


# The school's learning platform: which CLI reads it and what to tell the
# student when its sign-in lapses. Any other kind (or no host) means none.
LMS_CLI = {"brightspace": ("brightspace", "bs", "bs login"),
           "canvas": ("canvas", "canvas", "canvas login")}
LMS = PROFILE["lms"]["kind"] if PROFILE["lms"].get("host") and PROFILE["lms"]["kind"] in LMS_CLI else None
BS = connector(*LMS_CLI[LMS or "brightspace"][:2])



plugins.load(PROFILE["plugins"])

def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 1, "", str(exc)


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------

def last_line(text):
    """The bottom line of a traceback - the part that says what broke.

    Storing the first 200 characters of a stack trace records the interpreter
    boilerplate and truncates before the actual exception, which is how a
    dead session hid behind `File "bs", line 1162, in <module>` for days.
    """
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return lines[-1].strip() if lines else "failed"


def brightspace_items(errors):
    """Deadlines/announcements/grades from the school's platform (Brightspace
    or Canvas, see LMS), keyed by its course id."""
    if not LMS:
        return {}
    src, login = LMS, LMS_CLI[LMS][2]
    code, out, err = run([sys.executable, BS, "feed", "--max-age", "900"], timeout=420)
    if code != 0:
        # Degrade, don't disappear. A failed refetch must not empty every
        # course in the planner - the connector keeps its own cache, so ask
        # for that before giving up. Losing a class to a network blip is the
        # exact failure this whole thing exists to prevent.
        why = last_line(err or out)
        code2, out2, err2 = run([sys.executable, BS, "feed", "--cached"], timeout=90)
        if code2 != 0:
            errors.append({"source": src, "error": why[:200]})
            return {}
        errors.append({"source": src,
                       "error": "live fetch failed, showing cache: %s" % why[:160]})
        out = out2
    try:
        feed = json.loads(out)
    except ValueError:
        errors.append({"source": src, "error": "unparseable feed"})
        return {}
    # The connector degrades to cache on a dead session and still exits 0 -
    # correct behaviour, but it means a silently expiring Brightspace login
    # looks exactly like a healthy sync from out here. The stale flag is the
    # only tell, so surface it loudly rather than quietly serving old work.
    if feed.get("stale"):
        age = ""
        ts = parse_dt(feed.get("fetchedAt"))
        if ts:
            age = ", %d h old" % int((now_utc() - ts).total_seconds() // 3600)
        errors.append({"source": src,
                       "error": "serving cached data%s - session expired, run: %s" % (age, login)})
    by_course = {}
    for it in feed.get("items", []):
        cid = (it.get("meta") or {}).get("courseId")
        if cid is not None:
            by_course.setdefault(str(cid), []).append(it)
    return by_course


MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def sheet_deadlines(url, year, errors, label):
    """Parse the math schedule CSV - the ONLY place its HW/quiz dates exist."""
    code, out, err = run(["curl", "-sSL", "-m", "45", "--compressed", url], timeout=60)
    if code != 0:
        errors.append({"source": label, "error": err.strip()[:200]})
        return []
    items = []
    try:
        rows = list(csv.reader(io.StringIO(out)))
    except Exception as exc:
        errors.append({"source": label, "error": str(exc)})
        return []
    # The Recitations column keeps its own rhythm, three cells to a cycle -
    # "Friday", then "Recitation N", then "Quiz N" - and none of the three
    # belong to the date on their own row. A quiz listed beside Monday is sat
    # in the Friday recitation before it, which is why every quiz was showing
    # up on the wrong day: the parser stamped the row date on whatever it
    # found to the right of it.
    recit_col = None
    for row in rows:
        for i, c in enumerate(row):
            if c.strip().lower().startswith("recitation"):
                recit_col = i
                break
        if recit_col is not None:
            break

    from datetime import timedelta
    for row in rows:
        cells = [c.strip() for c in row]
        # rows look like: #, Day, 14-Sep, Lesson, "Homework 1 (1,2,3)", "Quiz 1 (1)"
        date_cell = next((c for c in cells if re.match(r"^\d{1,2}-[A-Za-z]{3}$", c)), None)
        if not date_cell:
            continue
        day, mon = date_cell.split("-")
        month = MONTHS.get(mon[:3].title())
        if not month:
            continue
        try:
            # The sheet gives a date and no time, so "end of that day" is the
            # only honest reading - and end of day is local. Pinning it to
            # 23:59 UTC showed every math deadline as 7:59pm, which is not a
            # time anybody sets a deadline at.
            when = datetime(year, month, int(day), 23, 59,
                            tzinfo=COURSE_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
        idx = cells.index(date_cell)
        for col, c in enumerate(cells):
            if col <= idx:
                continue
            if not re.match(r"(?i)^(homework|hw|quiz|exam|midterm|final|project)\b", c):
                continue
            due = when
            if recit_col is not None and col == recit_col:
                # Back up to the Friday this recitation actually met on.
                local = when.astimezone(COURSE_TZ)
                while local.weekday() != WEEKDAYS["Friday"]:
                    local -= timedelta(days=1)
                due = local.astimezone(timezone.utc)
            items.append({
                "title": c, "due": iso(due), "source": label,
                "url": url.replace("/pub?output=csv", "/pubhtml"),
            })
    return items


WEEKDAYS = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6}

# Recurring times in the registry are written the way a syllabus writes them -
# "due Mondays by 6:00 p.m." is 18:00 in New York, not 18:00 UTC. Reading them
# as UTC put every weekly deadline four hours early, and would have drifted to
# five the moment the clocks changed in November.
try:
    from zoneinfo import ZoneInfo
    COURSE_TZ = ZoneInfo(PROFILE["timezone"])
except Exception:
    COURSE_TZ = timezone.utc


def recurring_deadlines(course, weeks=4):
    """Expand rules like 'due Mondays by 6:00 p.m.' into real dates.

    Some courses never publish a single dated deadline - the only statement of
    when work is due is one sentence in the syllabus. Without this they look
    like they have no work at all.
    """
    out = []
    from datetime import timedelta
    for r in course.get("recurring", []) or []:
        wd = WEEKDAYS.get(r.get("weekday", ""))
        if wd is None:
            continue
        hh, mm = (r.get("time") or "23:59").split(":")
        # Bare "2026-09-08" parses naive; comparing it to an aware datetime
        # raises. Coerce both ends to UTC.
        def aware(x):
            if x is None:
                return None
            return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
        start = aware(parse_dt(r.get("from"))) or now_utc()
        until = aware(parse_dt(r.get("until")))
        # A bare date means "through that day", not "up to midnight that
        # morning". Read literally it deleted the last session of the term:
        # until 2026-12-11 excluded the 9am class on 2026-12-11.
        if until and len(str(r.get("until") or "")) == 10:
            until += timedelta(days=1)
        # Weeks a class does not meet - Thanksgiving, spring break - would
        # otherwise generate a deadline for a session that never happens.
        skip = set(r.get("skip") or [])
        # Anchor on the local date: near midnight UTC the local day is still
        # yesterday, which would shift the whole series by a week.
        d = now_utc().astimezone(COURSE_TZ).date()
        d += timedelta(days=(wd - d.weekday()) % 7)
        for _ in range(weeks):
            when = datetime(d.year, d.month, d.day, int(hh), int(mm),
                            tzinfo=COURSE_TZ).astimezone(timezone.utc)
            if d.isoformat() in skip:
                d += timedelta(days=7)
                continue
            if when >= start and (not until or when <= until):
                out.append({"title": r.get("title", "Assignment"), "due": iso(when),
                            "source": r.get("source", "syllabus"), "url": "",
                            "recurring": True})
            d += timedelta(days=7)
    return out


def drop_covered_recurring(deadlines):
    """Discard syllabus placeholders for slots a real assignment now fills.

    A syllabus states the rule ("weekly assignments are due Mondays by 6pm");
    Brightspace states the instance ("Assignment 1: Disruption"). Both describe
    the same Monday, so the planner shows the week's work twice - once with a
    title and a link, once as a bare "Weekly assignment" that cannot be opened
    or found, because there is nothing on the far end of it to find.

    The placeholder exists to keep a course from looking empty before anything
    is posted, so it is only ever a stand-in. Once the real item lands it has
    done its job. Matching is by local calendar day rather than by timestamp:
    an instructor who posts a Monday assignment at 5pm instead of 6 has not
    created a second assignment.
    """
    real = set()
    for d in deadlines:
        if d.get("recurring"):
            continue
        when = parse_dt(d.get("due"))
        if when:
            real.add(when.astimezone(COURSE_TZ).date())
    if not real:
        return deadlines
    out = []
    for d in deadlines:
        when = parse_dt(d.get("due")) if d.get("recurring") else None
        if when and when.astimezone(COURSE_TZ).date() in real:
            continue
        out.append(d)
    return out


def registry_deadlines(course):
    """Assignments recorded by hand because they are published as prose."""
    out = []
    for a in (course.get("assignments") or {}).get("items", []) or []:
        if a.get("due"):
            # Numbered ones read "Assignment 3: ..."; one-off tasks from an
            # email ("send your blog link") have no number and keep their name.
            title = a.get("title", "")
            if a.get("n"):
                title = "Assignment %s: %s" % (a["n"], title)
            out.append({
                "title": title,
                "due": iso(parse_dt(a["due"])) if parse_dt(a["due"]) else a["due"],
                "source": "syllabus",
                "url": a.get("submitVia", ""),
                "parts": a.get("parts", []),
            })
    return out


CW = connector("campuswire", "cw")


def campuswire_items(course, errors):
    """Class feed posts. Instructors put real work here, not only in the LMS."""
    src = next((s for s in course.get("sources", []) if s["kind"] == "campuswire"), None)
    if not src:
        return []
    m = re.search(r"/c/([A-Za-z0-9]+)", src.get("url", ""))
    if not m:
        return []
    code, out, err = run([sys.executable, CW, "--group", m.group(1),
                          "posts", "--limit", "20", "--json"], timeout=300)
    if code != 0:
        errors.append({"source": "campuswire", "error": last_line(err or out)[:160]})
        return []
    try:
        posts = json.loads(out)
    except ValueError:
        return []
    msgs = []
    for p in posts if isinstance(posts, list) else []:
        msgs.append({
            "title": p.get("title") or "(untitled)",
            "at": p.get("createdAt") or p.get("created_at"),
            "body": re.sub(r"<[^>]+>", " ", p.get("body") or p.get("content") or "")[:400],
            "source": "campuswire",
        })
    return msgs


DC = connector("discord", "dc")


def discord_items(course, errors):
    """Messages from a server's channels. The mentorship lives entirely on
    Discord - there is no site and no LMS - so this is its only source.

    The source names the guild and the channels to read (ids, from `dc
    channels`); a source with only an invite url is a link, not a feed."""
    src = next((s for s in course.get("sources", []) if s["kind"] == "discord"), None)
    if not src or not src.get("guild") or not src.get("channels"):
        return []
    chans = src["channels"]
    ids = ",".join(chans.keys() if isinstance(chans, dict) else chans)
    code, out, err = run([sys.executable, DC, "posts", "--guild", str(src["guild"]),
                          "--channels", ids, "--limit", "12", "--json"], timeout=600)
    if code != 0:
        errors.append({"source": "discord", "error": last_line(err or out)[:160]})
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    for e in data.get("errors") or []:
        errors.append({"source": "discord", "error": str(e)[:160]})
    msgs = []
    for it in data.get("items") or []:
        meta = it.get("meta") or {}
        chan = (it.get("context") or {}).get("channel") or ""
        # the page title reads "AStudio: announcements"; keep the channel
        chan = chan.split(": ")[-1]
        msgs.append({
            "title": "#%s \u00b7 %s: %s" % (chan, meta.get("author") or "?", it.get("title") or ""),
            "at": it.get("at"),
            "body": (meta.get("body") or "")[:400],
            "url": it.get("url"),
            "links": meta.get("links") or [],
            "source": "discord",
        })
    return msgs


# npm's global bin is not on launchd's PATH either; look there by hand.
GWS = shutil.which("gws") or next(
    (p for p in (os.path.expanduser("~/.npm-global/bin/gws"), "/usr/local/bin/gws",
                 "/opt/homebrew/bin/gws") if os.path.exists(p)), "")


def _gws(args, timeout=60):
    code, out, err = run([GWS] + args, timeout=timeout)
    if code != 0:
        raise RuntimeError(last_line(err or out)[:160])
    # gws prints a keyring notice on stderr and JSON on stdout
    return json.loads(out)


def gmail_items(course, errors, limit=8):
    """Recent mail matching the course's own Gmail query (`course.gmail.query`).

    Mentorship producers and some instructors only ever email; a calendar
    invite or a shared folder is the whole announcement. Reads through the
    gws CLI (OAuth) - subject, sender, date and snippet,
    never the full body."""
    q = (course.get("gmail") or {}).get("query")
    if not q:
        return []
    if not GWS:
        errors.append({"source": "gmail", "error": "gws CLI not found"})
        return []
    try:
        listing = _gws(["gmail", "users", "messages", "list", "--params",
                        json.dumps({"userId": "me", "q": q, "maxResults": limit})])
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        errors.append({"source": "gmail", "error": str(exc)[:160]})
        return []
    msgs = []
    for m in (listing.get("messages") or [])[:limit]:
        try:
            full = _gws(["gmail", "users", "messages", "get", "--params",
                         json.dumps({"userId": "me", "id": m["id"], "format": "metadata",
                                     "metadataHeaders": ["Subject", "From", "Date"]})])
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            continue
        hdr = {h["name"]: h["value"] for h in (full.get("payload") or {}).get("headers", [])}
        sender = re.sub(r"\s*<[^>]*>", "", hdr.get("From", "")).strip('" ')
        try:
            at = datetime.fromtimestamp(int(full.get("internalDate", 0)) / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            at = None
        msgs.append({
            "title": "\u2709 %s: %s" % (sender or "?", hdr.get("Subject") or "(no subject)"),
            "at": iso(at) if at else None,
            "body": (full.get("snippet") or "")[:400],
            "url": "https://mail.google.com/mail/u/0/#all/%s" % m["id"],
            "source": "gmail",
        })
    return msgs


GH_STATE = os.path.expanduser("~/.github-watch.json")
GH_API = "https://api.github.com"

def gh_skip(path):
    """True for repo furniture, as opposed to coursework.

    Only the ROOT readme is furniture. A readme *inside* a folder is the
    assignment itself - that is precisely how the ML-for-Arts repo publishes
    every week (01-introduction/README.md), so matching on the basename alone
    would hide the one file that matters.
    """
    base = os.path.basename(path).lower()
    if base.startswith(".") or base in ("license", "license.md", ".ds_store"):
        return True
    return "/" not in path and base in ("readme", "readme.md")


def load_gh_state():
    try:
        with open(GH_STATE) as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except (IOError, ValueError):
        return {}


def save_gh_state(state):
    tmp = GH_STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, GH_STATE)


def gh_get(url, errors, label):
    """Unauthenticated GitHub API GET. Returns parsed JSON, or None on failure."""
    code, out, err = run(
        ["curl", "-sSL", "-m", "25", "-H", "Accept: application/vnd.github+json", url],
        timeout=45)
    if code != 0:
        errors.append({"source": label, "error": last_line(err)[:160]})
        return None
    try:
        data = json.loads(out)
    except ValueError:
        errors.append({"source": label, "error": "unparseable response"})
        return None
    # A rate limit or 404 comes back as an object carrying only a message.
    if isinstance(data, dict) and set(data) <= {"message", "documentation_url", "status"}:
        errors.append({"source": label, "error": str(data.get("message", ""))[:160]})
        return None
    return data


def gh_repos(course):
    """(owner, repo) per GitHub source. A wiki is the same repo - dedupe it.

    Every kind of course-content repo counts. Watching only "github" and
    "github-wiki" meant one class's weekly-notes repo was checked purely by
    accident - it happens to also be listed as the wiki, and the two URLs
    reduce to the same pair. A course that listed only its notes repo got no
    change detection at all. Her own repo is deliberately absent: pushes there
    are her work, not the class posting something new, and they already reach
    the planner as "started".
    """
    seen, out = set(), []
    for src in course.get("sources", []) or []:
        if src.get("kind") not in ("github", "github-wiki",
                                   "github-weekly", "github-wiki-assignments"):
            continue
        m = re.search(r"github\.com/([^/]+)/([^/#?]+)", src.get("url", "") or "")
        if not m:
            continue
        pair = (m.group(1), m.group(2).replace(".git", ""))
        if pair in seen:
            continue
        seen.add(pair)
        out.append(pair)
    return out


WEEK_ROW = re.compile(r"^\|\s*(\d{1,2})\.?\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|")
HW_HEAD = re.compile(r"^##\s+Homework\s+Week\s*(\d+)", re.I)
WEEK_FILE = re.compile(r"^weeks/(\d{2})[_-]")
# Instructors state the cost in whatever words they like - "budget 6 to 9 hours"
# in one class, "expect to spend 3 to 6 hours a week" in another. Both are
# the same fact and both beat anything a title can imply.
BUDGET = re.compile(
    r"(?:budget|spend|expect(?:ed)?\s+to\s+spend)\D{0,24}?"
    r"(\d+)\s*(?:to|-|\u2013)\s*(\d+)\s*hours?", re.I)


def raw_url(owner_repo, path):
    return "https://raw.githubusercontent.com/%s/HEAD/%s" % (owner_repo, path)


def fetch_text(url, errors, label):
    code, out, err = run(["curl", "-sSL", "-m", "20", url], timeout=40)
    if code != 0:
        errors.append({"source": label, "error": last_line(err)[:160]})
        return ""
    return out


WIKI_WEEK = re.compile(r"(?i)^\W*week\s*(\d{1,2})\s+homework")


def wiki_submissions(course, errors, my_repo):
    """Which weeks she has actually handed in, per the class wiki.

    The wiki home page is the ledger the class actually runs on - each week has
    a links section and students add a line pointing at their own repo. That is
    a stronger signal than a folder existing locally: a folder means started,
    a line on the wiki means handed in.

    Matched on the repo URL rather than the nickname, because a student's wiki
    nickname and their GitHub name often differ.
    """
    src = next((x for x in course.get("sources", []) or []
                if x.get("kind") == "github-wiki"), None)
    if not src or not my_repo:
        return {}
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", src.get("url", "") or "")
    if not m:
        return {}
    repo = m.group(2).replace(".wiki", "").replace(".git", "")
    text = fetch_text(
        "https://raw.githubusercontent.com/wiki/%s/%s/Home.md" % (m.group(1), repo),
        errors, "wiki:%s" % repo)
    if not text:
        return {}
    found, week = {}, None
    for line in text.splitlines():
        head = WIKI_WEEK.match(line.strip().lstrip("#*").strip())
        if head:
            week = int(head.group(1))
            continue
        if week is None or my_repo.lower() not in line.lower():
            continue
        link = re.search(r"\((https?://[^)]+)\)", line)
        found[week] = {"url": link.group(1) if link else None,
                       "line": line.strip("- ").strip()[:120]}
    return found


SESSION_ROW = re.compile(r"^###\s*(\d+)\s*:.*?\((\d{1,2})/(\d{1,2})\)\s*$")
ASSIGN_SESSION_LINK = re.compile(
    r"described on the [^\]]*\]\((https://github\.com/[^)#]+)(#[^)]*)?\)", re.I)
POST_BY = re.compile(r"post by\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
POSTED_HEAD = re.compile(r"(?i)^##+\s*post your work")


def wiki_assignments(course, errors, state, who=None,
                     ahead_days=28, behind_days=7):
    """Assignments that live on a class wiki, one page per assignment.

    Some classes publish `Assignment-N` wiki pages that point at the real
    text on that session's page and collect everyone's submitted links. Dates
    come from the session schedule in the README plus the syllabus rule that
    work is due by class time one week after it is assigned.
    """
    who = who or PROFILE["githubWikiName"] or PROFILE["name"]
    src = next((x for x in course.get("sources", []) or []
                if x.get("kind") == "github-wiki-assignments"), None)
    if not src:
        return []
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", src.get("url", "") or "")
    if not m:
        return []
    owner, repo = m.group(1), m.group(2).replace(".wiki", "").replace(".git", "")
    key, label = "%s/%s" % (owner, repo), "wiki-assign:%s" % repo

    readme = fetch_text(raw_url(key, "README.md"), errors, label)
    sessions, titles, year = {}, {}, now_utc().year
    for line in readme.splitlines():
        flat = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).strip()
        row = SESSION_ROW.match(flat)
        if row:
            n = int(row.group(1))
            sessions[n] = (int(row.group(2)), int(row.group(3)))
            # "### 3: Pre-trained models 1: Body (9/18)" -> "Pre-trained models 1: Body"
            titles[n] = re.sub(r"\s*\(\d{1,2}/\d{1,2}\)\s*$", "",
                               flat.split(":", 1)[1]).strip()
    if not sessions:
        errors.append({"source": label, "error": "no session schedule in README"})
        return []

    seen = state.setdefault("wiki:%s" % key, {})
    b = BUDGET.search(readme)
    if b:
        seen["budgetHours"] = (int(b.group(1)) + int(b.group(2))) / 2.0

    hh, mm = ((course.get("meets") or {}).get("start") or "17:00").split(":")
    now, out = now_utc(), []
    for n in sorted(sessions):
        nxt = sessions.get(n + 1)
        if not nxt:
            continue
        page = fetch_text(
            "https://raw.githubusercontent.com/wiki/%s/Assignment-%d.md" % (key, n),
            errors, label)
        if not page:
            continue

        hour, minute = int(hh), int(mm)
        t = POST_BY.search(page)
        if t:
            hour = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "pm" else 0)
            minute = int(t.group(2) or 0)
        due = datetime(year, nxt[0], nxt[1], hour, minute,
                       tzinfo=COURSE_TZ).astimezone(timezone.utc)
        age = (due - now).total_seconds() / 86400.0
        if age > ahead_days or age < -behind_days:
            continue

        # The wiki page points at the session page; that is where the actual
        # task is written. The wiki itself only ever says "do the thing there".
        body = ""
        link = ASSIGN_SESSION_LINK.search(page)
        if link:
            path = link.group(1).split("/tree/main/", 1)[-1].strip("/")
            sess = fetch_text(raw_url(key, "%s/README.md" % path), errors, label)
            grab, grabbing = [], False
            for line in sess.splitlines():
                if re.match(r"(?i)^##+\s*assignment\b", line):
                    grabbing = True
                    continue
                if grabbing and re.match(r"^##\s", line):
                    break
                if grabbing:
                    grab.append(line)
            body = "\n".join(grab).strip()

        topic = titles.get(n, "")
        item = {
            "title": "Assignment %d%s" % (n, (": " + topic) if topic else ""),
            "due": iso(due),
            "source": "class wiki",
            "url": "https://github.com/%s/wiki/Assignment-%d" % (key, n),
            "body": body[:1200],
        }
        if seen.get("budgetHours"):
            item["hoursHint"] = seen["budgetHours"]

        # Everyone posts their link under "Post your work"; hers being absent
        # is the whole question.
        posting, mine_line = False, None
        for line in page.splitlines():
            if POSTED_HEAD.match(line.strip()):
                posting = True
                continue
            if posting and re.search(r"(?i)\b%s\b" % re.escape(who), line):
                mine_line = line.strip("- ").strip()
        if mine_line:
            item["status"] = "done"
            item["handedIn"] = {"line": mine_line[:120]}
        out.append(item)
    return out


def weekly_homework(course, errors, state, ahead_days=28, behind_days=7):
    """Turn each week's `## Homework WeekNN` section into a real deadline.

    A course taught out of a repo of weekly notes has no assignment list to
    read - the homework IS a section of that week's markdown, and it is written
    the week before it is due. A generic "weekly exercise" placeholder gets the
    cadence right and tells her nothing about what the work actually is, which
    is the only part that helps her start.

    Only the weeks near now are fetched: the whole term is 14 files, and
    re-reading all of them every two hours to learn nothing is rude to someone
    else's server.
    """
    src = next((s for s in course.get("sources", []) or []
                if s.get("kind") == "github-weekly"), None)
    if not src:
        return []
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", src.get("url", "") or "")
    if not m:
        return []
    key = "%s/%s" % (m.group(1), m.group(2).replace(".git", ""))
    label = "github-weekly:%s" % m.group(2)

    readme = fetch_text(raw_url(key, src.get("readme", "README.md")), errors, label)
    schedule = {}
    for line in readme.splitlines():
        row = WEEK_ROW.match(line.strip())
        if row:
            schedule[int(row.group(1))] = row.group(2)
    if not schedule:
        errors.append({"source": label, "error": "no week/date table in README"})
        return []

    tree = gh_get("%s/repos/%s/git/trees/HEAD?recursive=1" % (GH_API, key), errors, label)
    by_week = {}
    for t in (tree or {}).get("tree", []) or []:
        f = WEEK_FILE.match(t.get("path") or "")
        if t.get("type") == "blob" and f and (t["path"].endswith(".md")):
            by_week.setdefault(int(f.group(1)), []).append(t["path"])

    hh, mm = ((course.get("meets") or {}).get("start") or "09:00").split(":")
    now = now_utc()
    out = []
    # "budget 6 to 9 hours for your homework assignments" is said once, in
    # week 1, about every week. Remember it: by October that file is outside
    # the fetch window and the guidance would otherwise be forgotten.
    seen = state.setdefault("weekly:%s" % key, {})

    # Her own class repo, if registered: a WeekNN folder in it is the handin.
    # Knowing a week is already underway is the difference between a nag and
    # a status, and this planner nagging about work already done is exactly
    # how she would stop trusting it.
    mine, handed_in = {}, {}
    mysrc = next((x for x in course.get("sources", []) or []
                  if x.get("kind") == "github-mine"), None)
    if mysrc:
        mm_ = re.search(r"github\.com/([^/]+)/([^/#?]+)", mysrc.get("url", "") or "")
        if mm_:
            mykey = "%s/%s" % (mm_.group(1), mm_.group(2).replace(".git", ""))
            mytree = gh_get("%s/repos/%s/git/trees/HEAD?recursive=1" % (GH_API, mykey),
                            errors, "github-mine:%s" % mm_.group(2))
            for t in (mytree or {}).get("tree", []) or []:
                path = t.get("path") or ""
                w = re.match(r"(?i)^week[ _-]?(\d{1,2})", path)
                if not w or t.get("type") != "blob":
                    continue
                slot = mine.setdefault(int(w.group(1)),
                                       {"files": 0, "repo": mykey,
                                        "root": path.split("/")[0]})
                slot["files"] += 1
            for wk, slot in mine.items():
                slot["url"] = "https://github.com/%s/tree/HEAD/%s" % (
                    slot["repo"], slot["root"])
            handed_in = wiki_submissions(course, errors, mykey)
    for week in sorted(by_week):
        # Homework set in week N is due when week N+1 meets.
        nxt = schedule.get(week + 1)
        if not nxt:
            continue
        y, mo, dd = (int(x) for x in nxt.split("-"))
        due = datetime(y, mo, dd, int(hh), int(mm),
                       tzinfo=COURSE_TZ).astimezone(timezone.utc)
        age = (due - now).total_seconds() / 86400.0
        if age > ahead_days or age < -behind_days:
            continue

        # A week can have more than one file: a week 4 can have 04_DataModel.md
        # beside 04_swiftui.md, and only the second holds the homework. Taking
        # just the first file dropped that week from the planner without a word.
        text = ""
        for path in by_week[week]:
            body = fetch_text(raw_url(key, path), errors, label)
            lines = body.splitlines()
            topic = ""
            if lines and lines[0].startswith("# "):
                topic = re.sub(r"^#\s*Week\s*\d+\s*", "", lines[0]).strip(" ,-")

            section, grabbing = [], False
            for line in lines:
                if HW_HEAD.match(line):
                    grabbing = True
                    continue
                if grabbing and line.startswith("## "):
                    break
                if grabbing:
                    section.append(line)
            text = "\n".join(section).strip()
            if text:
                break
        if not text:
            continue

        item = {
            "title": "Week %02d homework%s" % (week, (": " + topic) if topic else ""),
            "due": iso(due),
            "source": "class repo",
            "url": "https://github.com/%s/blob/HEAD/%s#homework-week%02d" % (key, path, week),
            "body": re.sub(r"<!--.*?-->", "", text, flags=re.S)[:1200].strip(),
        }
        # The instructor states the cost outright - "budget 6 to 9 hours". That
        # beats anything the scorer can infer from a title, so pass it through.
        if week in mine:
            item["mine"] = mine[week]
            item["status"] = "started"
        if week in handed_in:
            item["handedIn"] = handed_in[week]
            item["status"] = "done"
        b = BUDGET.search(text)
        if b:
            item["hoursHint"] = (int(b.group(1)) + int(b.group(2))) / 2.0
            seen["budgetHours"] = item["hoursHint"]
        out.append(item)

    # A week that states no budget of its own inherits the course-wide one.
    if seen.get("budgetHours"):
        for item in out:
            item.setdefault("hoursHint", seen["budgetHours"])
    return out




def gdoc_watch(course, errors, state):
    """Notice a syllabus being rewritten mid-term.

    Three courses state their real rules only in a published Google Doc - how
    long weekly work should take, what the late policy is, when the exam is.
    Those were registered as sources and then never read, so a syllabus could
    be rewritten in week 6 and nothing would say so.

    Only a change is reported, never the contents: the document is the
    instructor's to present, and a diff of it is not something this planner
    should be putting on screen. Text is normalised before hashing because
    Google's export re-wraps lines on its own schedule.
    """
    out = []
    for src in course.get("sources", []) or []:
        if src.get("kind") != "gdoc" or not src.get("url"):
            continue
        label = "syllabus:%s" % course["key"]
        body = fetch_text(src["url"], errors, label)
        if not body:
            continue
        norm = " ".join(body.split())
        if len(norm) < 200:          # an error page, not a syllabus
            continue
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        seen = state.setdefault("gdoc:%s" % course["key"], {})
        prev = seen.get("sha")
        seen["sha"] = digest
        seen["chars"] = len(norm)
        if prev and prev != digest:
            out.append({"title": "Syllabus updated", "path": src.get("role") or "syllabus",
                        "url": src["url"], "status": "modified",
                        "at": iso(now_utc()), "repo": course.get("short") or course["name"]})
    return out


def github_watch(course, errors, state, commit_days=21, keep_days=14):
    """Watch a class repo for file changes, not just commit subjects.

    For a course taught out of GitHub the push IS the homework posting, and
    the commit subject routinely says nothing about what landed ("Add files
    via upload"). So diff the repo against the sha we saw last run and report
    the actual paths that were added or edited.

    Changes are kept for `keep_days` rather than only reported the once, so a
    file that appeared on Tuesday is still visible in the planner on Friday.

    Returns (materials, changes, messages).
    """
    materials, changes, msgs = [], [], []
    now = now_utc()

    for owner, repo in gh_repos(course):
        key = "%s/%s" % (owner, repo)
        label = "github:%s" % repo
        prev = state.get(key) or {}

        commits = gh_get("%s/repos/%s/commits?per_page=10" % (GH_API, key), errors, label)
        if not isinstance(commits, list) or not commits:
            # Keep showing what we already know rather than blanking the class.
            changes += prune_changes(prev.get("recent") or [], now, keep_days)
            continue

        head = commits[0].get("sha")
        cutoff = now.timestamp() - commit_days * 86400
        for c in commits:
            dt = parse_dt(((c.get("commit") or {}).get("author") or {}).get("date"))
            if not dt or dt.timestamp() < cutoff:
                continue
            msgs.append({
                "title": ((c.get("commit") or {}).get("message") or "").split("\n")[0][:120],
                "at": iso(dt), "body": key, "source": "github",
                "url": c.get("html_url", ""),
            })

        fresh = []
        base = prev.get("head")
        if base and head and base != head:
            cmp_ = gh_get("%s/repos/%s/compare/%s...%s" % (GH_API, key, base, head),
                          errors, label)
            # A force-push or a rewritten history 404s the compare. That is a
            # lost baseline, not a repo full of new homework - reset quietly.
            for f in (cmp_ or {}).get("files", []) or []:
                path = f.get("filename") or ""
                if not path or gh_skip(path):
                    continue
                when = parse_dt(((commits[0].get("commit") or {}).get("author") or {})
                                .get("date")) or now
                fresh.append({
                    "path": path,
                    "title": os.path.basename(path),
                    "module": path.split("/")[0] if "/" in path else key,
                    "status": f.get("status", "modified"),
                    "at": iso(when),
                    "url": f.get("blob_url") or "https://github.com/%s/blob/HEAD/%s" % (key, path),
                    "repo": key,
                })

        # newest wins if a path moved twice inside the window
        merged = {c["path"]: c for c in prune_changes(prev.get("recent") or [], now, keep_days)}
        for c in fresh:
            merged[c["path"]] = c
        recent = sorted(merged.values(), key=lambda c: c["at"], reverse=True)
        changes += recent

        tree = gh_get("%s/repos/%s/git/trees/HEAD?recursive=1" % (GH_API, key), errors, label)
        for t in (tree or {}).get("tree", []) or []:
            path = t.get("path") or ""
            if t.get("type") != "blob" or not path or gh_skip(path):
                continue
            materials.append({
                "title": os.path.basename(path),
                "module": path.split("/")[0] if "/" in path else key,
                "url": "https://github.com/%s/blob/HEAD/%s" % (key, path),
                "id": "github:%s:%s" % (key, path),
                "source": "github",
            })

        state[key] = {"head": head, "checkedAt": iso(now), "recent": recent,
                      "new": [c for c in fresh]}

    changes.sort(key=lambda c: c["at"], reverse=True)
    return materials, changes, msgs


def prune_changes(recent, now, keep_days):
    """Drop remembered changes older than the window."""
    cutoff = now.timestamp() - keep_days * 86400
    out = []
    for c in recent or []:
        dt = parse_dt(c.get("at"))
        if dt and dt.timestamp() >= cutoff and c.get("path"):
            out.append(c)
    return out


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def busy_blocks(reg):
    """Her Google Calendar: (busy blocks, all-day events, errors).

    Busy blocks are what the session planner must not use; all-day events are
    only shown on the week. `calendar.ics` is one secret-address url or a list
    of them (one per Google calendar). A feed that fails keeps whatever the
    last run wrote for it: an empty busy list would make Plan it schedule
    straight through her week, which is worse than a day-old one."""
    urls = (reg.get("calendar") or {}).get("ics")
    urls = [u for u in ([urls] if isinstance(urls, str) else urls or []) if u and u.strip()]
    if not urls:
        return [], [], []
    busy, all_day, errors, failed = [], [], [], False
    for url in urls:
        try:
            b, a = calendar_feed.fetch_calendar(url, tz_name=PROFILE["timezone"])
            busy += b
            all_day += a
        except Exception as exc:
            failed = True
            errors.append({"source": "calendar", "error": str(exc)[:160]})
    if failed:
        try:
            with open(CACHE) as f:
                prev = json.load(f)
            if not busy:
                busy = prev.get("busy") or []
            if not all_day:
                all_day = prev.get("allDay") or []
        except (IOError, ValueError):
            pass
    busy.sort(key=lambda b: b["start"])
    all_day.sort(key=lambda a: (a["date"], a["title"]))
    return busy, all_day, errors


def build():
    errors = []
    with open(REGISTRY) as f:
        reg = json.load(f)
    # Courses name their platform id as lmsId (any school) or brightspaceId
    # (older registries); everything below reads brightspaceId.
    for c in reg["courses"] + reg.get("ignore", []):
        if c.get("lmsId") and not c.get("brightspaceId"):
            c["brightspaceId"] = c["lmsId"]
    lms_src = LMS or "brightspace"

    gh_state = load_gh_state()
    bs_by_course = brightspace_items(errors)
    # Descriptions, where Brightspace bothered to give one. They are the only
    # real evidence of what an assignment involves, so the scorer gets them.
    bodies = {}
    for items in bs_by_course.values():
        for it in items:
            if it.get("kind") == "deadline" and (it.get("body") or "").strip():
                bodies[it["title"]] = it["body"]
    horizon_past = now_utc().timestamp() - 2 * 86400

    courses = []
    for c in reg["courses"]:
        deadlines, messages, materials, grade_items = [], [], [], []

        bid = c.get("brightspaceId")
        for it in bs_by_course.get(str(bid), []) if bid else []:
            if it["kind"] == "deadline" and it.get("at"):
                deadlines.append({"title": it["title"], "due": it["at"],
                                  "source": lms_src, "url": it.get("url", ""),
                                  "status": it.get("status"), "body": it.get("body") or ""})
            elif it["kind"] == "material":
                materials.append({"title": it["title"],
                                  "module": (it.get("meta") or {}).get("module", ""),
                                  "url": it.get("url", ""), "id": it["id"]})
            elif it["kind"] == "grade":
                grade_items.append(it)
            elif it["kind"] == "message":
                messages.append({"title": it["title"], "at": it.get("at"),
                                 "body": (it.get("body") or "")[:400],
                                 "source": lms_src})

        for src in c.get("sources", []):
            if src["kind"] == "gsheet-csv":
                # the sheet's dates carry no year: the term's start year, else this year
                year = int(str((c.get("term") or {}).get("start") or now_utc().year)[:4])
                deadlines += sheet_deadlines(src["url"], year, errors, "schedule sheet")

        deadlines += registry_deadlines(c)
        deadlines += plugins.course_items(c, errors)   # personal extras, e.g. one class's own website
        weekly = weekly_homework(c, errors, gh_state) + wiki_assignments(c, errors, gh_state)
        deadlines += weekly
        # The recurring rule is only a stand-in for weeks whose homework has
        # not been written yet; real parsed homework always wins. A course whose
        # assignments arrive from Brightspace rather than a notes repo parses no
        # weekly homework at all, so the stand-in has to be filtered against
        # every dated source, not just this one.
        if not weekly:
            deadlines += recurring_deadlines(c)
        deadlines = drop_covered_recurring(deadlines)
        messages += campuswire_items(c, errors)
        messages += discord_items(c, errors)
        messages += gmail_items(c, errors)
        gh_mats, gh_changes, gh_msgs = github_watch(c, errors, gh_state)
        materials += gh_mats
        messages += gh_msgs
        # A rewritten syllabus is a change to the course like any other.
        gh_changes = gdoc_watch(c, errors, gh_state) + gh_changes

        # future first, drop anything long past
        deadlines = [d for d in deadlines
                     if parse_dt(d["due"]) and parse_dt(d["due"]).timestamp() > horizon_past]
        deadlines.sort(key=lambda d: d["due"])
        messages.sort(key=lambda m: m.get("at") or "", reverse=True)

        # Discord arrives as a burst of one-liners; they are read together as
        # one digest, so they get their own quota rather than crowding the
        # other sources out of the eight.
        dc_msgs = [m for m in messages if m.get("source") == "discord"][:12]
        messages = sorted([m for m in messages if m.get("source") != "discord"][:8] + dc_msgs,
                          key=lambda m: m.get("at") or "", reverse=True)
        digest = None
        if dc_msgs:
            try:
                ai = os.environ.get("STUDY_SYNC_AI", "1") != "0"
                digest = discord_digest.build(c["key"], dc_msgs,
                                              **({} if ai else {"ask": lambda _p: ""}))
            except Exception as exc:
                errors.append({"source": "discord", "error": "summary: " + str(exc)[:140]})
        courses.append({
            "key": c["key"], "name": c["name"], "short": c.get("short") or c["name"],
            "hue": HUES[reg["courses"].index(c) % len(HUES)],
            "code": c.get("code"),
            "instructor": c.get("instructor"), "meets": c.get("meets"),
            "ta": c.get("ta"), "officeHours": c.get("officeHours"),
            "grading": c.get("grading"),
            # the syllabus attendance rule; her absences live in the ledger
            "attendance": c.get("attendance"),
            # her running average, from Brightspace scores and the syllabus weights
            "grades": grades.summarize(grade_items, c.get("gradeScheme")),
            "kit": c.get("kit") or {},
            "autoPlan": c.get("autoPlan") or {},
            "schedule": c.get("schedule") or [],
            "clientMeetings": c.get("clientMeetings") or {},
            "brightspaceId": bid,
            "links": [{"kind": s["kind"], "url": s.get("url"), "role": s.get("role"),
                       "access": s.get("access")} for s in c.get("sources", [])],
            "deadlines": deadlines[:12],
            "materials": materials,
            "messages": messages,
            "discordDigest": digest,
            "githubChanges": gh_changes[:20],
            "warning": c.get("warning") or c.get("note"),
            # how this instructor wants the work done - read by the brief writer
            "briefNotes": c.get("briefNotes") or "",
        })

    # A Brightspace course missing from the registry must still surface - the
    # registry is hand-maintained, and a silently dropped class is the exact
    # failure this whole thing exists to prevent.
    known = {str(c.get("brightspaceId")) for c in reg["courses"] if c.get("brightspaceId")}
    ignored = {str(i.get("brightspaceId")) for i in reg.get("ignore", [])}
    # Hand unregistered classes a hue nobody is already using. Hashing the org
    # unit id into the palette collided one class with a course that had just
    # appeared, and two classes sharing a colour is worse than no colour.
    # Sorted so the assignment is the same on every sync.
    spare = [h for h in HUES if h not in {c.get("hue") for c in courses}]
    for cid, items in sorted(bs_by_course.items()):
        if cid in known or cid in ignored:
            continue
        dl = [{"title": i["title"], "due": i["at"], "source": lms_src,
               "url": i.get("url", ""), "status": i.get("status"), "body": i.get("body") or ""}
              for i in items if i["kind"] == "deadline" and i.get("at")]
        dl = [d for d in dl if parse_dt(d["due"])
              and parse_dt(d["due"]).timestamp() > horizon_past]
        dl.sort(key=lambda d: d["due"])
        mats = [{"title": i["title"], "module": (i.get("meta") or {}).get("module", ""),
                 "url": i.get("url", ""), "id": i["id"]}
                for i in items if i["kind"] == "material"]
        # Surfacing an unregistered course matters only if it actually has work.
        # An empty old course is noise in the tab bar, not a missed class.
        if not dl and not mats:
            continue
        name = items[0]["context"] if items else "Course %s" % cid
        courses.append({
            "key": "bs-%s" % cid, "name": name, "short": (name or "")[:14],
            "hue": spare.pop(0) if spare else None,
            "code": None, "instructor": None, "meets": None, "ta": None,
            "officeHours": None, "grading": None, "brightspaceId": int(cid),
            "links": [], "deadlines": dl[:12], "materials": mats,
            "githubChanges": [],
            "messages": [{"title": i["title"], "at": i.get("at"),
                          "body": (i.get("body") or "")[:400], "source": lms_src}
                         for i in items if i["kind"] == "message"][:3],
            "warning": "Not in your course registry - add it to %s" % PROFILE["coursesPath"],
        })

    # soonest-deadline-first, classes with nothing due sink to the bottom
    courses.sort(key=lambda c: c["deadlines"][0]["due"] if c["deadlines"] else "9999")
    busy, all_day, busy_errors = busy_blocks(reg)
    errors += busy_errors
    feed = {"fetchedAt": iso(now_utc()), "courses": courses, "errors": errors,
            "studyPlaylist": reg.get("studyPlaylist"), "busy": busy, "allDay": all_day}
    # Stakes, effort and a date to START on. The rules layer always runs; the
    # model is asked only about work it has never seen, and only if it answers.
    try:
        prioritize.apply(feed, bodies=bodies,
                         ai=os.environ.get("STUDY_SYNC_AI", "1") != "0")
    except Exception as exc:
        errors.append({"source": "prioritize", "error": str(exc)[:160]})
    # Last, and never on the critical path: the deadlines are already in the
    # feed if this takes a while or fails.
    if os.environ.get("STUDY_SYNC_BRIEFS", "1") != "0":
        try:
            briefs.apply(courses, bodies=bodies)
        except Exception as exc:
            errors.append({"source": "briefs", "error": str(exc)[:160]})
    return feed, gh_state


LOCK = os.path.expanduser("~/.study-sync.lock")


def notify(title, msg):
    try:
        subprocess.run(["/usr/bin/osascript", "-e",
                        'display notification %s with title %s' %
                        (json.dumps(msg), json.dumps(title))], timeout=10)
    except Exception:
        pass


def is_gh(mat):
    return str(mat.get("id") or "").startswith("github:")


def new_materials(feed):
    """Ids present now that were absent last run - i.e. just posted.

    Brightspace only. GitHub runs its own sha-level diff in `githubWatch`,
    which also catches an edit to a file that already existed - something an
    id comparison can never see.
    """
    try:
        with open(CACHE) as f:
            prev = json.load(f)
    except (IOError, ValueError):
        return []          # first run: everything is "new", which is noise
    seen = set()
    for c in prev.get("courses", []):
        for m in c.get("materials", []) or []:
            if not is_gh(m):
                seen.add(m.get("id"))
    # A cache written before materials existed has none at all - that is a
    # missing baseline, not a course full of new files. Don't cry wolf.
    if not seen:
        return []
    fresh = []
    for c in feed["courses"]:
        for m in c.get("materials", []) or []:
            if m.get("id") and not is_gh(m) and m["id"] not in seen:
                fresh.append({"course": c["name"], "short": c.get("short"),
                              "title": m["title"], "module": m.get("module", "")})
    return fresh


def unseen_github(feed, gh_state):
    """File changes found on this run, flattened for the notification."""
    out = []
    for c in feed["courses"]:
        for ch in c.get("githubChanges", []) or []:
            entry = (gh_state.get(ch.get("repo")) or {}).get("new") or []
            if any(n.get("path") == ch.get("path") for n in entry):
                out.append({"course": c["name"], "short": c.get("short"),
                            "title": ch["path"], "status": ch.get("status", "")})
    return out


def main():
    # The in-app timer and the LaunchAgent can fire close together; two
    # concurrent runs would fight over the same agent-browser session.
    import fcntl
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print("another sync is already running; skipping")
        return 0

    if "--no-brief" in sys.argv:
        os.environ["STUDY_SYNC_BRIEFS"] = "0"
    feed, gh_state = build()
    fresh = new_materials(feed)
    gh_new = unseen_github(feed, gh_state)
    feed["newMaterials"] = fresh
    feed["newFiles"] = gh_new
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(feed, f, indent=2)
    os.replace(tmp, CACHE)
    # Only after the cache is safely on disk: advancing the watched sha is what
    # marks these changes as seen, and a crash between the two would report
    # them to nobody.
    save_gh_state(gh_state)
    total = sum(len(c["deadlines"]) for c in feed["courses"])
    print("Synced %d courses, %d deadlines -> %s" % (len(feed["courses"]), total, CACHE))
    if feed.get("focus"):
        print("\n  START THINKING ABOUT:")
        for f in feed["focus"]:
            print("    [%-6s] %-9s %-42s  start %s  ~%sh" % (
                f["band"], (f["course"] or "")[:9], (f["title"] or "")[:42],
                (f.get("startBy") or "?")[:10], f.get("hours")))
            if f.get("firstStep"):
                print("               first step: %s" % f["firstStep"])
    for c in feed["courses"]:
        nxt = c["deadlines"][0]["title"][:44] if c["deadlines"] else "-"
        print("  %-16s %2d due  next: %s" % (c["key"], len(c["deadlines"]), nxt))
    if fresh:
        print("\n  NEW material:")
        for m in fresh:
            print("    %s - %s%s" % (m["short"] or m["course"], m["title"],
                                     ("  [%s]" % m["module"]) if m["module"] else ""))
        head = fresh[0]
        notify("New course material",
               "%s: %s%s" % (head["short"] or head["course"], head["title"],
                             ("  +%d more" % (len(fresh) - 1)) if len(fresh) > 1 else ""))
    if gh_new:
        print("\n  CHANGED on GitHub:")
        for m in gh_new:
            print("    %s - %s (%s)" % (m["short"] or m["course"], m["title"],
                                        m["status"]))
        head = gh_new[0]
        notify("Class repo updated",
               "%s: %s%s" % (head["short"] or head["course"], head["title"],
                             ("  +%d more" % (len(gh_new) - 1)) if len(gh_new) > 1 else ""))

    for e in feed["errors"]:
        print("  ! %s: %s" % (e["source"], e["error"]), file=sys.stderr)

    # A lapsed login is the one failure that quietly rots the whole feed, so it
    # gets a notification rather than a line in a log nobody reads.
    dead = [e for e in feed["errors"]
            if "login" in e["error"].lower() or "expired" in e["error"].lower()]
    for e in dead:
        cmd = LMS_CLI[e["source"]][2] if e["source"] in LMS_CLI else "cw login"
        notify("Course sync needs you", "%s session expired. Run: %s" % (e["source"], cmd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
