# briefs.py
"""What an assignment actually is, in the order to do it.

Written once per assignment by the model at sync time and kept in
~/.assignment-briefs.json, so the page she taps into is already explained.
Re-asked only when the homework text itself changes. Any failure means no
brief, and the page shows the raw homework text instead - nothing waits on
this.
"""
from today_profile import PROFILE
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request

import assignment_context
import prioritize   # claude_bin(), parse_rows()

STORE = os.path.expanduser("~/.assignment-briefs.json")
ITP_PROXY = PROFILE.get("aiProxyUrl", "")   # a class AI proxy (Replicate-style), if the student has one
MAX_STEPS = 7
# Bump when the prompt changes: every brief is rewritten once under the new one.
PROMPT_VERSION = 3
CHUNK = 1           # assignments per model call - fewer means more care each
MAX_STEP_MIN = 240
MIN_STEP_MIN = 5

PROMPT = """You are a sharp TA sitting next to {learner} who is about \
to start one piece of coursework. She reads ONE step at a time on a timer \
screen ("Right now"), so every step must be something she can just do.

Use the evidence given for each assignment (its page, the schedule sheet, the \
lecture materials, the readings). Name the real things from it: the reading \
titles, the lecture topics, the exact questions, the model/library, the \
deliverable and where it is handed in.

Rules for steps:
- 3 to 7 steps, in order, covering the whole assignment through handing it in.
- Each "name" is an action on a specific thing, max 9 words: "Answer Q1: \
Disney brand qualities, cite the case", "Review Lesson 6: mean, median, \
standard deviation", "Read Cottom essay, mark 3 quotable lines".
- Each "how" is one concrete tip for doing that step well, max 22 words: \
what to look for, a method, a formula, a length, a shortcut.
- NEVER write filler steps: no "open the assignment/page/sheet", "confirm the \
due date", "copy the assignment text", "review the instructions", "do the \
readings", "gather materials", "get started". Opening a link is not a step.
- The first step must produce real progress within 15 minutes.
- The due date given is final and course notes override the evidence. Never \
tell her to check, confirm or verify a due date.
- Include the exact assignment title in its gist.
- Each brief belongs ONLY to its exact assignment id. Use its actual title, \
source instructions, named materials and deliverables; never reuse another assignment's outline.
- If the evidence is thin, say exactly what is missing. Never infer questions, \
rubrics, word counts, submission locations or lesson topics from a title.
- Propose steps only for work supported by the supplied evidence. Mark helpful \
suggestions as suggestions, not requirements. Fewer than three steps is fine \
when there is insufficient evidence for more.

Return ONLY a JSON array, one object per assignment, no prose, no code fence:
[{"id":"<id>","gist":"<1-2 sentences: what this is and exactly what gets handed in, where>",\
"steps":[{"name":"<max 9 words>","how":"<max 22 words>","minutes":<number>}],\
"watchOut":["<max 14 words each, 0-3 items: traps, requirements easy to miss, clashes>"]}]

Assignments:
%s
"""
PROMPT = PROMPT.replace("{learner}", PROFILE["learner"])   # profile["learner"], e.g. "a student"


def _local_due(due):
    """Her wall-clock due time. A UTC stamp's date is often the next day -
    11:59pm Monday is 03:59Z Tuesday - and the model then warned her that
    the homework was listed "a day early"."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        d = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
    except ValueError:
        return str(due or "")[:16]
    if d.tzinfo:
        d = d.astimezone(ZoneInfo(PROFILE["timezone"]))
    return d.strftime("%a %Y-%m-%d %H:%M")


def build_prompt(items):
    lines = []
    for it in items:
        parts = ["id=%s" % it["id"], "course=%s" % it.get("course", ""),
                 "due=%s" % _local_due(it.get("due")), "title=%s" % it.get("title", "")]
        if it.get("hours"):
            parts.append("estimate=%sh" % it["hours"])
        if it.get("body"):
            parts.append("text: " + re.sub(r"\s+", " ", str(it["body"]))[:1200])
        if it.get("materials"):
            parts.append("materials: " + "; ".join(str(m) for m in it["materials"][:6]))
        if it.get("notes"):
            parts.append("course notes: " + str(it["notes"])[:700])
        if it.get("context"):
            parts.append("evidence:\n    " + str(it["context"]).replace("\n", "\n    ")[:4000])
        lines.append("- " + " | ".join(parts))
    return PROMPT % "\n".join(lines)


# She confirmed her due dates; a warning that second-guesses one only adds doubt.
_DOUBTS_DUE = re.compile(r"(?i)(confirm|check|verify|which|clarify)\b[^.]*\b(due|date)\b|\b(due|date)\b[^.]*\?")


def validate(raw):
    """{id: {gist, steps, watchOut}} from model text; anything malformed is dropped."""
    rows = prioritize.parse_rows((raw or "").strip())
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "").strip()
        gist = str(r.get("gist") or "").strip()[:300]
        steps = []
        raw_steps = r.get("steps")
        for s in (raw_steps if isinstance(raw_steps, list) else [])[:MAX_STEPS]:
            if not isinstance(s, dict) or not str(s.get("name") or "").strip():
                continue
            try:
                minutes = int(round(float(s.get("minutes"))))
            except (TypeError, ValueError, OverflowError):
                continue
            step = {"name": str(s["name"]).strip()[:70],
                    "minutes": max(MIN_STEP_MIN, min(MAX_STEP_MIN, minutes))}
            how = str(s.get("how") or "").strip()
            if how:
                step["how"] = how[:160]
            steps.append(step)
        if not rid or not gist or not steps:
            continue
        raw_watch = r.get("watchOut")
        watch = [str(w).strip()[:160] for w in (raw_watch if isinstance(raw_watch, list) else [])[:4]
                 if str(w).strip() and not _DOUBTS_DUE.search(str(w))][:3]
        out[rid] = {"gist": gist, "steps": steps, "watchOut": watch}
    return out


def _ask_claude(prompt, timeout=240):
    exe = prioritize.claude_bin()
    if not exe:
        return ""
    try:
        with tempfile.TemporaryDirectory() as neutral:
            p = subprocess.run([exe, "-p", prompt, "--output-format", "text", "--tools", "", "--strict-mcp-config"],
                               capture_output=True, text=True, timeout=timeout, cwd=neutral)
    except Exception:
        return ""
    return p.stdout if p.returncode == 0 else ""


def _ask_itp(prompt, timeout=60):
    """A class AI proxy in front of gpt-4o-mini (profile["aiProxyUrl"]); none set means no fallback."""
    if not ITP_PROXY:
        return None
    body = json.dumps({"model": "openai/gpt-4o-mini",
                       "input": {"messages": [{"role": "user", "content": prompt}],
                                 "temperature": 0.3, "max_tokens": 1500}}).encode("utf-8")
    req = urllib.request.Request(ITP_PROXY, data=body, headers={"Content-Type": "application/json"})
    token = os.environ.get("ITP_PROXY_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return ""
    out = data.get("output") if isinstance(data, dict) else data
    if isinstance(out, list):
        out = "".join(str(x) for x in out)
    return str(out or "")


def ask(items):
    """Batched calls of CHUNK. claude first (what prioritize already relies
    on), the proxy if claude is missing or says nothing. {} on total failure."""
    out = {}
    for i in range(0, len(items), CHUNK):
        prompt = build_prompt(items[i:i + CHUNK])
        for backend in (_ask_claude, _ask_itp):
            wanted = {it["id"] for it in items[i:i + CHUNK]}
            got = {k: v for k, v in validate(backend(prompt)).items() if k in wanted}
            if got:
                out.update(got)
                break
    return out


def load():
    try:
        with open(STORE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (IOError, ValueError):
        return {}


def save(store):
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, STORE)


def _text_hash(d):
    fields = {k: d.get(k) for k in ("title", "body", "url", "due", "materials", "parts", "_courseContext")}
    raw = json.dumps([PROMPT_VERSION, fields], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def apply(courses, bodies=None, budget=8, enabled=True, gather=assignment_context.gather):
    """Attach `brief` to every deadline that has one; ask for the ones that
    don't, soonest due first, skipping what is already past."""
    store = load()
    bodies = bodies or {}
    pending, index, valid_hashes = [], {}, {}
    title_counts = {}
    for c in courses:
        for d in c.get("deadlines") or []:
            title_counts[d.get("title")] = title_counts.get(d.get("title"), 0) + 1
    now = prioritize.iso(prioritize.now_utc())
    for c in courses:
        for d in c.get("deadlines") or []:
            pid = (d.get("priority") or {}).get("id")
            if not pid:
                continue
            index[pid] = d
            body = (d.get("body") or bodies.get(pid) or bodies.get((c.get("key"), d.get("title")))
                    or (bodies.get(d.get("title")) if title_counts.get(d.get("title")) == 1 else "") or "")
            course_context = {k: c.get(k) for k in ("key", "briefNotes", "assignments", "warning", "materials")}
            h = _text_hash(dict(d, body=body, _courseContext=course_context))
            valid_hashes[pid] = h
            d.pop("brief", None)
            have = store.get(pid)
            if have and have.get("textHash") == h:
                continue
            if (d.get("due") or "9") < now[:10]:
                continue
            pending.append({"id": pid, "course": c.get("short") or c.get("name"),
                            "_course": c, "_deadline": d,
                            "title": d.get("title"), "due": d.get("due"),
                            "hours": (d.get("priority") or {}).get("hours"),
                            "body": body,
                            "materials": [m.get("title") for m in (d.get("materials") or []) if isinstance(m, dict)],
                            "notes": " ".join(x for x in (c.get("briefNotes") or "",
                                                          (c.get("assignments") or {}).get("submitVia") or c.get("warning") or "") if x),
                            "_hash": h})
    if enabled and pending:
        pending.sort(key=lambda it: it.get("due") or "9")
        batch = pending[:budget]
        cache = {}
        for it in batch:
            try:
                it["context"] = gather(it["_course"], it["_deadline"], cache) if gather else ""
            except Exception:
                it["context"] = ""
        fresh = ask(batch)
        for it in batch:
            b = fresh.get(it["id"])
            if b:
                store[it["id"]] = dict(b, textHash=it["_hash"], madeAt=prioritize.iso(prioritize.now_utc()))
        if fresh:
            save(store)
        for it in batch:
            it.pop("_course", None); it.pop("_deadline", None)
    for pid, b in store.items():
        d = index.get(pid)
        if d and b.get("textHash") == valid_hashes.get(pid):
            d["brief"] = {"gist": b["gist"], "steps": b["steps"], "watchOut": b.get("watchOut") or [],
                          "madeAt": b.get("madeAt")}
