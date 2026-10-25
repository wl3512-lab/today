"""The internship agent inside Today: the Internships page, its résumé chat and the "Run now" button.

A core plugin, loaded when the profile's features include "internships"
(plugins.names_for). The agent itself is its own repo, found by agent_path;
this file only wires its tracker and tools to the planner's server. Nothing
here submits an application.
"""
import os
from urllib.parse import parse_qs, urlparse

import agent_path  # noqa: F401  (the internship agent, from its GitHub clone)
import ai_help
import intern_chat
import intern_fill
import intern_run
import internships
from today_profile import PROFILE

# the Internships page and résumé chat load from the agent's clone, so the window must be allowed to read it
READ_ROOTS = [agent_path.REPO]

# /internships/run starts an agent with shell access; the résumé chat runs Claude Code
KEYED_ROUTES = ("/internships/run", "/internships/chat")

POST_ROUTES = {
    # Two writers - the page and the scout job - so this
    # merges by id and never replaces the document.
    "/internships": internships.apply,
    "/internships/open": internships.open_local,
    # fills in a visible browser and stops before submit;
    # returns at once, progress lands on the posting
    "/internships/fill": intern_fill.start,
    "/internships/fill/show": intern_fill.show,
    # the daily scout + agent, now; the page polls action=status
    "/internships/run": intern_run.handle,
    "/internships/chat/open": intern_chat.open_for,
    "/internships/chat": intern_chat.chat_for,
    "/internships/chat/reset": intern_chat.reset_for,
}


def page_data(profile=None):
    """The tracker, plus the student's places (best first) for the page's location tags and filter."""
    data = internships.load()
    data["places"] = [{"group": t["group"], "label": t.get("label") or t["group"]}
                      for t in internships.config.places(profile)]
    return data


def handle_get(h):
    if h.path == "/internships":
        h._send_json(page_data())
        return True
    if h.path.startswith("/internships/file?"):
        _send_download(h)
        return True
    return False


def download_name(full, p=PROFILE):
    name = os.path.basename(full)
    if name in ("resume.pdf", "cover-letter.pdf"):
        # "resume.pdf" x twenty in Downloads is useless; name it for the job
        name = "%s_%s_%s" % ((p.get("fullName") or "Resume").replace(" ", "_"),
                             os.path.basename(os.path.dirname(full))[:60], name)
    return name


def _send_download(h):
    """A tailored résumé as a real download. The link carries the
    planner's key (a GET cannot send a body) and the path must resolve
    inside the drafts folder."""
    q = parse_qs(urlparse(h.path).query)
    if not ai_help.authorized({"token": (q.get("token") or [""])[0]}):
        h._send_json({"error": "reopen the planner from the menu bar"}, status=403)
        return
    full = intern_chat.safe_file((q.get("path") or [""])[0])
    if not full:
        h._send_json({"error": "no such draft"}, status=404)
        return
    with open(full, "rb") as fh:
        body = fh.read()
    name = download_name(full)
    ctype = {"pdf": "application/pdf", "md": "text/markdown; charset=utf-8",
             "html": "text/html; charset=utf-8",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
             }.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Disposition", 'attachment; filename="%s"' % name.replace('"', ""))
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)
