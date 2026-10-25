"""What an assignment actually asks, gathered for the brief writer.

Most deadlines arrive as a title and a link. A brief written from a title is
generic ("open the schedule sheet", "do the readings"), which is no help at
the moment she sits down. This collects the evidence that already exists
somewhere public:

  - the assignment's own page, or the section of it its #anchor points at
    (class site exercises, GitHub wiki pages, course repo markdown)
  - the schedule sheet rows that name it, and the lessons it covers
  - the course's lecture materials for the lessons in "(6, 7)"
  - the readings/videos attached to it

Brightspace instructions come through her logged-in `bs` CLI (read-only).
Everything is best-effort: a page that will not load is simply left out.
"""
from today_profile import PROFILE
import csv
import html as htmlmod
import io
import json
import os
import re
import subprocess

BS = os.path.expanduser("~/.claude/skills/brightspace/bs")
LE = "/d2l/api/le/1.74"

TIMEOUT = 15
PAGE_CHARS = 2500

# public hosts only - nothing behind the school login. Course sites a student's classes use go in profile["publicHosts"].
BUILTIN_PUBLIC = ["github.com", "githubusercontent.com", "docs.google.com/spreadsheets"]


def is_public(url, p=None):
    hosts = BUILTIN_PUBLIC + list((p or PROFILE)["publicHosts"])
    return bool(re.match(r"^https?://([^/]*\.)?(" + "|".join(re.escape(h) for h in hosts) + ")", url or "", re.I))


def fetch(url, cache=None):
    if cache is not None and url in cache:
        return cache[url]
    try:
        p = subprocess.run(["curl", "-sSL", "-m", str(TIMEOUT), "-A", "Mozilla/5.0 TodayPlanner/1.0", url],
                           capture_output=True, text=True, timeout=TIMEOUT + 5)
        text = p.stdout if p.returncode == 0 else ""
    except Exception:
        text = ""
    if cache is not None:
        cache[url] = text
    return text


def html_text(raw):
    raw = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|li|tr|h\d|div)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = htmlmod.unescape(raw)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    return re.sub(r"\n\s*\n+", "\n", raw).strip()


def section(raw_html, anchor, limit=PAGE_CHARS):
    """Text from the element named by #anchor onward."""
    m = re.search(r"""(?i)(id|name)\s*=\s*["']%s["']""" % re.escape(anchor), raw_html)
    if not m:
        # a class site's #weekN is not an id: cut "Week N" .. "Week N+1" from the text
        wk = re.match(r"(?i)week(\d+)$", anchor)
        if wk:
            n = int(wk.group(1))
            text = html_text(raw_html)
            a = re.search(r"(?m)^\s*Week %d\s*$" % n, text)
            if a:
                b = re.search(r"(?m)^\s*Week %d\s*$" % (n + 1), text[a.end():])
                return text[a.start():a.end() + (b.start() if b else limit)][:limit]
        return ""
    start = raw_html.rfind("<", 0, m.start())
    fragment = raw_html[max(0, start):]
    opening = re.match(r"<([a-zA-Z0-9]+)\b[^>]*>", fragment)
    if opening and opening.group(1).lower() in ("div", "section", "article", "tr", "li"):
        tag, depth = opening.group(1), 0
        for token in re.finditer(r"</?" + re.escape(tag) + r"\b[^>]*>", fragment, re.I):
            depth += -1 if token.group().startswith("</") else 1
            if depth == 0:
                fragment = fragment[:token.end()]
                break
    else:
        # Heading/empty-anchor sections end at the next heading or named anchor.
        tail = fragment[opening.end():] if opening else fragment
        boundary = re.search(r'<h[1-6]\b|<(?:a|div|section)\b[^>]*(?:id|name)\s*=', tail, re.I)
        if boundary:
            fragment = fragment[:(opening.end() if opening else 0) + boundary.start()]
    return html_text(fragment)[:limit]


def github_raw(url):
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/([^#?]+)", url)
    if m:
        return "https://raw.githubusercontent.com/%s/%s/%s/%s" % m.groups()
    # a folder link shows its README
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/([^#?]+?)/?$", url)
    return "https://raw.githubusercontent.com/%s/%s/%s/%s/README.md" % m.groups() if m else None


def page_text(url, cache=None, limit=PAGE_CHARS, _seen=None):
    if not url or not is_public(url) or "/spreadsheets/" in url:
        return ""
    _seen = set() if _seen is None else _seen
    if url in _seen or len(_seen) >= 5:
        return ""
    _seen.add(url)
    base, _, anchor = url.partition("#")
    raw_url = github_raw(base)
    if raw_url:
        md = fetch(raw_url, cache)
        if anchor and md:
            # markdown heading ids are the slugged heading text
            words = anchor.replace("-", " ").split()[:3]
            m = re.search(r"(?im)^#+ .*%s.*$" % r".*".join(map(re.escape, words)), md) if words else None
            if m:
                return md[m.start():m.start() + limit]
        return md[:limit]
    raw = fetch(base, cache)
    if not raw:
        return ""
    if anchor:
        got = section(raw, anchor, limit=limit)
        return got
    if "github.com" in base and "/wiki/" in base:
        m = re.search(r'(?is)<div[^>]+class="[^"]*markdown-body[^"]*"[^>]*>(.*)', raw)
        if m:
            raw = m.group(1)
        text = html_text(raw)[:limit]
        # "Complete the assignment as described on the Session 3 page": the
        # wiki page is a pointer, the work is on the page it names
        ref = re.search(r"(?i)described on the (Session \d+) page", text)
        if ref:
            link = re.search(r"""(?is)<a[^>]+href=["']([^"']+)["'][^>]*>[^<]*%s page[^<]*</a>""" % re.escape(ref.group(1)), raw)
            if link:
                href = link.group(1)
                if href.startswith("/"):
                    href = "https://github.com" + href
                more = page_text(href, cache, limit=limit, _seen=_seen) if href != url else ""
                if more:
                    text = text[:600] + "\n" + ref.group(1) + " page: " + more
        return text[:limit * 2]
    return html_text(raw)[:limit]


def bracket_numbers(title):
    """"Homework 3 (6, 7)" -> [6, 7]: the lessons it covers, not its own number."""
    m = re.search(r"\(([\d,\s&and-]+)\)", title or "")
    return [int(n) for n in re.findall(r"\d+", m.group(1))] if m else []


def lesson_materials(course, title):
    nums = bracket_numbers(title)
    out = []
    for m in course.get("materials") or []:
        t = m.get("title") or ""
        if any(re.search(r"\b(lesson|lecture|week|session)\s*#?\s*0?%d\b" % n, t, re.I) for n in nums):
            if t not in out:
                out.append(t)
    return out[:8]


def sheet_rows(url, title, cache=None):
    """Schedule-sheet rows that name this assignment or its lessons."""
    if not url or "/spreadsheets/" not in url:
        return []
    csv_url = re.sub(r"/pub(html)?(\?.*)?$", "/pub?output=csv", url.split("#")[0])
    text = fetch(csv_url, cache)
    if not text or text.lstrip().startswith("<"):
        return []
    own = re.match(r"\s*([A-Za-z]+\s*\d+)", title or "")
    keys = [own.group(1).lower()] if own else []
    keys += ["lesson %d " % n for n in bracket_numbers(title)] + ["lesson %d -" % n for n in bracket_numbers(title)]
    rows = []
    for row in csv.reader(io.StringIO(text)):
        line = " | ".join(c.strip() for c in row if c.strip())
        low = line.lower() + " "
        if line and any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\d)", low) for k in keys) and line not in rows:
            rows.append(line)
    return rows[:8]


def _bs(path):
    if not os.path.exists(BS):
        return None
    try:
        p = subprocess.run([BS, "api", path], capture_output=True, text=True, timeout=40)
        return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else None
    except Exception:
        return None


def brightspace_text(url, limit=PAGE_CHARS):
    """Instructions of a Brightspace dropbox folder or discussion topic."""
    if not url or not PROFILE["lms"]["host"] or PROFILE["lms"]["host"] not in url:
        return ""
    m = re.search(r"[?&]db=(\d+).*?[?&]ou=(\d+)|[?&]ou=(\d+).*?[?&]db=(\d+)", url)
    if m:
        db, ou = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        d = _bs("%s/%s/dropbox/folders/%s" % (LE, ou, db)) or {}
        return html_text((d.get("CustomInstructions") or {}).get("Html") or
                         (d.get("CustomInstructions") or {}).get("Text") or "")[:limit]
    m = re.search(r"/d2l/le/(\d+)/discussions/topics/(\d+)", url)
    if m:
        ou, tid = m.groups()
        for f in _bs("%s/%s/discussions/forums/" % (LE, ou)) or []:
            t = _bs("%s/%s/discussions/forums/%s/topics/%s" % (LE, ou, f.get("ForumId"), tid))
            if t and t.get("TopicId"):
                desc = (t.get("Description") or {})
                forum = html_text((f.get("Description") or {}).get("Html") or "")
                return (html_text(desc.get("Html") or desc.get("Text") or "") + "\n" + forum)[:limit]
    return ""


def gather(course, deadline, cache=None):
    """A compact evidence string for one assignment ('' when there is none)."""
    parts = []
    title, url = deadline.get("title") or "", deadline.get("url") or ""
    page = page_text(url, cache) or brightspace_text(url)
    if page:
        parts.append("assignment page: " + re.sub(r"\s+", " ", page)[:PAGE_CHARS])
    rows = sheet_rows(url, title, cache)
    if rows:
        parts.append("schedule sheet: " + " // ".join(rows))
    lessons = lesson_materials(course, title)
    if lessons:
        parts.append("lecture materials for it: " + "; ".join(lessons))
    mats = [m for m in deadline.get("materials") or [] if isinstance(m, dict)]
    if mats:
        parts.append("readings/media: " + "; ".join(
            "%s (%s%s)" % (m.get("title"), m.get("kind") or "read",
                           ", no link - find it" if m.get("search") else "") for m in mats))
    if deadline.get("parts"):
        parts.append("parts: " + re.sub(r"\s+", " ", str(deadline["parts"]))[:500])
    return "\n".join(parts)
