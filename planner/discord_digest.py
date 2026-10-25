"""Discord, summarised: one box per server instead of a row per message.

A busy channel filled the incoming feed with one-line fragments ("Yea that
works", "Okay great") that say nothing on their own. This reads the recent
messages together and writes one or two plain sentences on what the
conversation is about and anything asked of her.

Summaries are cached by the exact set of messages, so a sync with nothing new
never calls the model, and a failed call is never cached - the next sync
tries again. Without a model the box still says who talked where; it never
guesses at what they said.
"""
from today_profile import PROFILE
import hashlib
import json
import os
import re
import tempfile

import prioritize

STORE = os.path.expanduser("~/.discord-digests.json")
HER = PROFILE["discordName"]
TIMEOUT = 180

PROMPT = """These are recent messages from a Discord server {name} (Discord name {her}) \
is in, oldest first.

{lines}

In one or two short, plain sentences, say what this conversation is about and \
whether anything is asked of {name} or waiting on her. Address her as "you". \
Use people's names as written. No preamble, no bullet points, no quotes."""


def make_prompt(lines, p=None):
    p = p or PROFILE
    return PROMPT.format(name=p["name"], her=p["discordName"], lines=lines)

_TITLE = re.compile(r"^#([^\s·]+)\s·\s@?([^:]+):")


def _who_where(m):
    g = _TITLE.match(m.get("title") or "")
    return (g.group(1), g.group(2).strip()) if g else ("", "")


def _load(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def ask_claude(prompt):
    exe = prioritize.claude_bin()
    if not exe:
        return ""
    import subprocess
    try:
        with tempfile.TemporaryDirectory() as neutral:
            p = subprocess.run([exe, "-p", prompt, "--output-format", "text"],
                               capture_output=True, text=True, timeout=TIMEOUT, cwd=neutral)
    except Exception:
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def build(key, messages, path=STORE, ask=ask_claude):
    msgs = [m for m in messages or [] if m.get("source") == "discord"]
    if not msgs:
        return None
    msgs.sort(key=lambda m: m.get("at") or "")
    channels, people = [], []
    for m in msgs:
        ch, who = _who_where(m)
        if ch and ch not in channels:
            channels.append(ch)
        if who and who != HER and who not in people:
            people.append(who)
    people = sorted(people, key=lambda p: -max(i for i, m in enumerate(msgs) if _who_where(m)[1] == p))
    latest = msgs[-1]
    sig = hashlib.sha1("\n".join((m.get("at") or "") + (m.get("title") or "") for m in msgs).encode()).hexdigest()[:16]

    names = people[0] if len(people) == 1 else ", ".join(people[:-1]) + " and " + people[-1] if people else "people"
    fallback = "%d messages in %s from %s" % (len(msgs), ", ".join("#" + c for c in channels) or "Discord", names)

    store = _load(path)
    cached = store.get(key) or {}
    summary = cached.get("summary", "") if cached.get("sig") == sig else ""
    if not summary:
        lines = "\n".join("[#%s] %s: %s" % (_who_where(m)[0], _who_where(m)[1] or "?",
                                             re.sub(r"\s+", " ", m.get("body") or m.get("title") or "")[:300])
                          for m in msgs)
        summary = (ask(make_prompt(lines)) or "").strip()
        if summary:
            store[key] = {"sig": sig, "summary": summary}
            _save(path, store)
    return {"summary": summary, "fallback": fallback, "count": len(msgs), "channels": channels,
            "people": people, "latestAt": latest.get("at"), "url": latest.get("url")}
