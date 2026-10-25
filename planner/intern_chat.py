"""The internship chat: tailor a résumé for one job, then download it.

A panel on the Internships page talks to headless Claude Code working in
~/.internship-chat. That folder holds what the resume-tailoring skill
(github.com/varunr89/resume-tailoring-skill, loaded with --plugin-dir) expects -
a `resumes/` library of their real résumé, CV and cover letter as Markdown - plus
CLAUDE.md (the rules, see rules_path) and CONTEXT.md (the postings they have open right now).

It can read the drafts folders, add a pasted posting through intern_add.py,
write a tailored résumé.html into a posting's folder and print it with
intern_render.py. It cannot submit anything, touch their master résumé, or run
any other command. Every PDF it writes during a turn comes back to the page as
a download button.
"""
import json
import os
import re
import shutil
import subprocess
import time

import agent_path  # noqa: F401  (agent modules come from the GitHub clone)
import ai_help
import internships
import intern_tailor
import prioritize
from today_profile import PROFILE as _P, planner_path

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, ".internship-chat")
DRAFTS = internships.DRAFTS
SKILL = os.path.expanduser((_P.get("internships") or {}).get("tailorSkill") or "~/claude-repos/resume-tailoring-skill")
# their master résumé, copied in as template/ so the chat can never edit the real one ("" = none)
MASTER_HTML = os.path.expanduser((_P.get("internships") or {}).get("masterResume") or "")
PROFILE = internships.config.PROFILE
PLANNER = agent_path.SCRIPTS            # where the five allowed scripts live
TURN_TIMEOUT = 600
OPEN = ("new", "needs_info", "ready")
DOWNLOADABLE = (".pdf", ".md", ".docx", ".html")

TOOLS = "Read,Glob,Grep,Edit,Write,Bash,WebFetch,WebSearch,Skill"
COMMANDS = ["intern_add.py", "intern_render.py", "resume_tailor.py", "resume_check.py",
            "intern_tailor.py brief"]


def allowed_tools(planner=PLANNER):
    # Bash only for these five scripts, by absolute path - nothing else runs
    bash = ["Bash(python3 %s:*)" % os.path.join(planner, c) for c in COMMANDS]
    return ",".join(["Read", "Glob", "Grep", "Edit", "Write", "WebFetch", "WebSearch", "Skill"] + bash)


def rules_path(p=None):
    """The chat's rules: the shared internship_chat_rules.md, or the student's own file."""
    p = p if p is not None else _P
    return planner_path((p.get("internships") or {}).get("chatRules") or "internship_chat_rules.md")


def claude_md(p=None, places=None):
    """CLAUDE.md for the chat folder: the rules filled in for this student and this Mac."""
    p = p if p is not None else _P
    s = p.get("internships") or {}
    places = places if places is not None else internships.config.places()
    groups = [t["group"] for t in places if t.get("group")] + ["remote_global", "remote_us", "us", "other"]
    facts = (s.get("facts") or "").strip() or (
        "only what `resumes/` says. Ask before assuming anything else (a GPA, a visa, a graduation date).")
    with open(rules_path(p)) as fh:
        text = fh.read()
    return text.format(skill=SKILL, planner=PLANNER, name=p.get("name") or "the student", facts=facts,
                       groups="/".join(groups), extra_rules="".join("- %s\n" % r for r in s.get("extraRules") or []))


def _text(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def build_library(root=ROOT, profile_path=PROFILE, p=None):
    """Their own documents as Markdown, rewritten on every open so an edit to
    their profile (a GPA, a date) reaches the next tailoring pass."""
    lib = os.path.join(root, "resumes")
    os.makedirs(lib, exist_ok=True)
    try:
        with open(profile_path) as f:
            prof = json.load(f)
    except (OSError, ValueError):
        prof = {}
    p = p if p is not None else _P
    who = re.sub(r"[^a-z0-9]+", "-", (p.get("fullName") or p.get("name") or "").lower()).strip("-") or "student"
    docs = {who + "-resume.md": ("Résumé", prof.get("resume_text")),
            who + "-cv.md": ("CV", prof.get("cv_text")),
            who + "-cover-letter.md": ("Cover letter (reference for their voice)", prof.get("cover_letter_text"))}
    written = []
    for name, (title, body) in docs.items():
        if body:
            ai_help._atomic(os.path.join(lib, name), "# %s\n\n%s\n" % (title, body.strip()))
            written.append(name)
    return written


def context_md(data):
    lines = ["# Open postings", "",
             "id | company | role | status | fit | deadline | drafts folder", "--- | --- | --- | --- | --- | --- | ---"]
    rows = [p for p in data.get("postings") or [] if p.get("status") in OPEN]
    rows.sort(key=lambda p: (p.get("status") != "ready", -(p.get("fit") or 0)))
    for p in rows:
        lines.append(" | ".join(str(x) for x in (
            p.get("id"), p.get("company"), (p.get("role") or "")[:70], p.get("status"),
            p.get("fit") or "", p.get("deadline") or "", os.path.basename(intern_tailor.folder(p)))))
    if not rows:
        lines.append("(none open)")
    lines += ["", "Drafts live in %s/<folder>/." % DRAFTS]
    return "\n".join(lines) + "\n"


def prepare(root=ROOT, data=None):
    os.makedirs(root, exist_ok=True)
    with ai_help._lock(root):
        build_library(root)
        tpl = os.path.join(root, "template")
        os.makedirs(tpl, exist_ok=True)
        if os.path.exists(MASTER_HTML):
            shutil.copy2(MASTER_HTML, os.path.join(tpl, "resume.html"))
        ai_help._atomic(os.path.join(root, "CLAUDE.md"), claude_md())
        ai_help._atomic(os.path.join(root, "CONTEXT.md"), context_md(data if data is not None else internships.load()))
    return root


def new_files(since, drafts=None):
    """Files written into any drafts folder during a turn, newest first."""
    drafts = drafts or DRAFTS
    out = []
    try:
        folders = [d for d in os.listdir(drafts) if os.path.isdir(os.path.join(drafts, d))]
    except OSError:
        return out
    for d in folders:
        for name in os.listdir(os.path.join(drafts, d)):
            p = os.path.join(drafts, d, name)
            if (name.endswith(".pdf") and not name.endswith(".prev.pdf")
                    and os.path.getmtime(p) >= since):
                out.append({"folder": d, "name": name, "path": "%s/%s" % (d, name),
                            "at": os.path.getmtime(p)})
    out.sort(key=lambda f: -f["at"])
    return out


def command(message, exe, sid=None, planner=PLANNER):
    cmd = [exe, "-p", message, "--output-format", "json",
           "--tools", TOOLS, "--allowedTools", allowed_tools(planner),
           "--add-dir", DRAFTS, "--strict-mcp-config"]
    if os.path.isdir(os.path.join(SKILL, ".claude-plugin")):
        cmd += ["--plugin-dir", SKILL, "--add-dir", SKILL]
    if sid:
        cmd += ["--resume", sid]
    return cmd


def chat(message, root=ROOT, runner=subprocess.run, exe=None, clock=time.time):
    message = (message or "").strip()
    if not message:
        return {"reply": "", "messages": ai_help.load_chat(root), "files": []}
    with ai_help._lock(root):
        started = clock() - 1
        if not exe:
            reply, sid = "Couldn't find the claude command on this Mac.", None
        else:
            try:
                p = runner(command(message, exe, ai_help._session(root)), capture_output=True,
                           text=True, timeout=TURN_TIMEOUT, cwd=root)
                reply, sid = _parse(p)
            except subprocess.TimeoutExpired:
                reply, sid = "That took over ten minutes, so I stopped it. Try one job at a time.", None
            except Exception as exc:
                reply, sid = "Claude didn't start: %s" % exc, None
        if sid:
            ai_help._write(root, ai_help.SESSION, {"id": sid})
        files = new_files(started)
        msgs = ai_help.load_chat(root) + [{"role": "me", "text": message},
                                          {"role": "claude" if sid else "error", "text": reply, "files": files}]
        ai_help._write(root, ai_help.TRANSCRIPT, msgs)
    return {"reply": reply, "messages": msgs, "files": files}


def _parse(p):
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip().splitlines()
        return "Claude hit an error: %s" % (err[-1] if err else "exit %s" % p.returncode), None
    try:
        out = json.loads(p.stdout)
    except ValueError:
        return "Claude's answer came back garbled - try again.", None
    if not isinstance(out, dict) or out.get("is_error") or not (out.get("result") or "").strip():
        return "Claude hit an error: %s" % str((out or {}).get("result") or "empty reply")[:200], None
    return out["result"].strip(), out.get("session_id")


def reset(root=ROOT):
    for name in (ai_help.SESSION, ai_help.TRANSCRIPT):
        try:
            os.remove(os.path.join(root, name))
        except OSError:
            pass
    return {"messages": []}


def safe_file(rel, drafts=None):
    """The absolute path of a drafts file the student may download, or None."""
    drafts = drafts or DRAFTS
    rel = (rel or "").strip().lstrip("/")
    if not rel or not rel.lower().endswith(DOWNLOADABLE):
        return None
    root = os.path.realpath(drafts)
    full = os.path.realpath(os.path.join(root, rel))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        return None
    return full


# --- what the server calls ---------------------------------------------------

def open_for(_body):
    prepare()
    return {"messages": ai_help.load_chat(ROOT)}


def chat_for(body):
    prepare()
    return chat(body.get("message"), exe=prioritize.claude_bin())


def reset_for(_body):
    return reset()
