#!/usr/bin/env python3
"""Find anything personal in the files git would publish: names, handles, school links, private links, keys, health notes.

    python3 tools/privacy_scan.py            exit 1 and list hits if anything is found
Run before every publish (Part 3 makes it a pre-push hook). Words to look for come from the built-in list
below plus the owner's own ~/.today/profile.json (name, handles, notes link), so it catches what is theirs.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTIN = [
    r"calendar\.google\.com/calendar/ical", r"\bghp_[A-Za-z0-9]{20,}", r"\bsk-[A-Za-z0-9]{20,}", r"xox[bp]-",
    r"notion\.so/[a-z0-9]+/", r"discord\.com/channels/\d{6,}", r"(?<![\d.])\d{17,19}(?![\d.])",   # Discord ids
    r"\bADHD\b", r"smok(e|ing|ed)\b", r"\bnicotine\b",
    r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b",                                                # phone numbers
]
# this file's own pattern list is fine
ALLOW_FILES = {"tools/privacy_scan.py"}
# Known, reviewed hits that are not personal data: (file, text that may match).
ALLOW_HITS = []


def owner_words(path=None):
    """Words that are the owner's: from their real settings file (not a test profile), when this Mac has one."""
    try:
        p = json.load(open(os.path.expanduser(path or os.environ.get("TODAY_OWNER_PROFILE", "~/.today/profile.json"))))
    except (OSError, ValueError):
        return []
    words = [p.get("fullName"), p.get("discordName"), p.get("githubWikiName"), p.get("notesUrl"), (p.get("lms") or {}).get("host")]
    words += [p.get("name")] if len(p.get("name") or "") > 3 else []
    words += [s.get("professor") for s in ((p.get("quizPrep") or {}).get("settings") or {}).values()]
    return [re.escape(w) for w in words if w and len(w) > 3]


def tracked_files():
    # tracked files plus new ones git would add (not ignored), so it also catches what isn't committed yet
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split("\n")
    return [f for f in out if f and f not in ALLOW_FILES]


def scan(files=None, patterns=None):
    pats = [re.compile(p, re.I) for p in (patterns or BUILTIN + owner_words())]
    hits = []
    for f in files or tracked_files():
        path = os.path.join(ROOT, f)
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            for p in pats:
                m = p.search(line)
                if m and not any(f == af and re.search(ar, line, re.I) for af, ar in ALLOW_HITS):
                    hits.append((f, i, m.group(0), line.strip()[:110]))
    return hits


if __name__ == "__main__":
    found = scan()
    for f, i, word, line in found:
        print("%s:%d  [%s]  %s" % (f, i, word, line))
    print("%d personal-looking hits" % len(found))
    sys.exit(1 if found else 0)
