"""The in-session Claude helper: its workspace, its context, its turns."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_help

DEADLINE = {
    "title": "Week 03 homework: Swift UI 1, Images",
    "due": "2026-09-30T23:59:00",
    "url": "https://github.com/cs110/wiki/Week-03",
    "priority": {"id": "abc123def456", "hours": 3.0, "remaining": 2.5,
                 "firstStep": "Open the starter project", "why": ["due Wednesday"]},
    "brief": {"gist": "Make a SwiftUI view that shows three images.",
              "steps": [{"name": "Add images to Assets", "minutes": 10, "how": "drag them in"}]},
}
COURSE = {"key": "coding", "short": "Coding", "name": "Intro to Programming",
          "code": "CS 110", "instructor": "Prof X",
          "links": [{"kind": "site", "url": "https://cs110.example", "role": "class site"}],
          "deadlines": [DEADLINE]}
CACHE = {"courses": [COURSE]}
LEDGER = {"sessions": [{"minutes": 25, "deadlineId": "abc123def456"},
                       {"minutes": 10, "deadlineId": "other"}],
          "notes": {"abc123def456": {"text": "stuck on the grid layout"}},
          "steps": {"coding": [{"text": "ask TA about assets"}]}}


class Done:
    def __init__(self, out, code=0, err=""):
        self.stdout, self.returncode, self.stderr = out, code, err


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_find_by_priority_id(self):
        c, d = ai_help.find(CACHE, "coding", "abc123def456")
        self.assertIs(d, DEADLINE)
        self.assertEqual(ai_help.find(CACHE, "coding", "nope"), (None, None))

    def test_slug_is_stable_and_safe(self):
        s = ai_help.slug(COURSE, DEADLINE)
        self.assertEqual(s, ai_help.slug(COURSE, DEADLINE))
        self.assertRegex(s, r"^[a-z0-9-]+$")
        self.assertTrue(s.startswith("coding-week-03-homework"))
        self.assertRegex(s, r"-[a-f0-9]{20}$")

    def test_context_has_everything_she_would_have_to_explain(self):
        md = ai_help.context_md(COURSE, DEADLINE, "assignment page: build a grid", LEDGER)
        for bit in ("Week 03 homework", "Intro to Programming", "2026-09-30",
                    "three images", "Add images to Assets", "stuck on the grid layout",
                    "25 min", "ask TA about assets", "assignment page: build a grid",
                    "https://github.com/cs110/wiki/Week-03", "https://cs110.example"):
            self.assertIn(bit, md)
        self.assertNotIn("35 min", md)          # other assignments' time is not this one's

    def read(self, folder, name):
        with open(os.path.join(folder, name)) as f:
            return f.read()

    def test_prepare_gathers_once_and_refreshes_context(self):
        calls = []
        def gather(c, d):
            calls.append(1)
            return "evidence text"
        folder = ai_help.prepare(COURSE, DEADLINE, LEDGER, root=self.root, gather=gather,
                                 source=lambda d: "")
        self.assertTrue(os.path.exists(os.path.join(folder, "CLAUDE.md")))
        self.assertIn("evidence text", self.read(folder, "CONTEXT.md"))
        led2 = dict(LEDGER, notes={"abc123def456": {"text": "grid done, now captions"}})
        ai_help.prepare(COURSE, DEADLINE, led2, root=self.root, gather=gather, source=lambda d: "")
        self.assertEqual(len(calls), 1)
        self.assertIn("now captions", self.read(folder, "CONTEXT.md"))

    def test_failed_gather_is_retried_next_open(self):
        calls = []
        def gather(c, d):
            calls.append(1)
            return ""
        for _ in range(2):
            folder = ai_help.prepare(COURSE, DEADLINE, LEDGER, root=self.root, gather=gather,
                                     source=lambda d: "")
        self.assertEqual(len(calls), 2)
        self.assertIn("could not be fetched", self.read(folder, "CONTEXT.md"))

    def test_full_source_is_kept_beside_the_context(self):
        rubric = "x" * 5000 + " RUBRIC: 9 photos exactly"
        folder = ai_help.prepare(COURSE, DEADLINE, LEDGER, root=self.root, gather=lambda c, d: "ev",
                                 source=lambda d: rubric)
        self.assertIn("RUBRIC: 9 photos exactly", self.read(folder, ai_help.SOURCE))
        self.assertIn(ai_help.SOURCE, self.read(folder, "CONTEXT.md"))

    def test_materials_keep_their_links(self):
        d = dict(DEADLINE, materials=[{"title": "Reading A", "url": "https://r.example/a"},
                                      {"title": "Film B", "kind": "watch", "search": True}])
        md = ai_help.context_md(COURSE, d, "", LEDGER)
        self.assertIn("Reading A (read): https://r.example/a", md)
        self.assertIn("Film B (watch): no link", md)

    def test_browser_progress_reaches_the_context(self):
        md = ai_help.context_md(COURSE, DEADLINE, "", LEDGER,
                                progress={"done": ["Add images to Assets"], "current": "Grid"})
        self.assertIn("- [x] Add images to Assets", md)
        self.assertIn("on now: Grid", md)
        self.assertEqual(ai_help.clean_progress("junk"), {"done": [], "current": ""})


class TokenTests(unittest.TestCase):
    def test_token_is_stable_private_and_required(self):
        path = os.path.join(tempfile.mkdtemp(), "tok")
        t = ai_help.token(path)
        self.assertEqual(t, ai_help.token(path))
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertTrue(ai_help.authorized({"token": t}, path))
        self.assertFalse(ai_help.authorized({"token": "guess"}, path))
        self.assertFalse(ai_help.authorized({}, path))


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.folder)

    def runner(self, reply="hi", sid="sess-1", code=0):
        def run(cmd, **kw):
            self.calls.append((cmd, kw))
            if code:
                return Done("", code, "boom")
            return Done(json.dumps({"result": reply, "session_id": sid}))
        return run

    def test_first_turn_starts_then_resumes(self):
        r = ai_help.chat(self.folder, "where do I start?", runner=self.runner(), exe="/bin/claude")
        self.assertEqual(r["reply"], "hi")
        cmd, kw = self.calls[0]
        self.assertEqual(cmd[:3], ["/bin/claude", "-p", "where do I start?"])
        self.assertNotIn("--resume", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], ai_help.PANEL_TOOLS)
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.assertEqual(kw["cwd"], self.folder)
        ai_help.chat(self.folder, "next?", runner=self.runner(sid="sess-1"), exe="/bin/claude")
        cmd2 = self.calls[1][0]
        self.assertEqual(cmd2[cmd2.index("--resume") + 1], "sess-1")

    def test_transcript_keeps_both_sides(self):
        ai_help.chat(self.folder, "q1", runner=self.runner("a1"), exe="/bin/claude")
        msgs = ai_help.load_chat(self.folder)
        self.assertEqual([(m["role"], m["text"]) for m in msgs], [("me", "q1"), ("claude", "a1")])

    def test_failure_is_a_reply_not_a_session(self):
        r = ai_help.chat(self.folder, "q", runner=self.runner(code=1), exe="/bin/claude")
        self.assertIn("boom", r["reply"])
        self.assertIsNone(ai_help._session(self.folder))

    def test_error_json_does_not_save_a_session(self):
        def run(cmd, **kw):
            return Done(json.dumps({"is_error": True, "result": "rate limited", "session_id": "x"}))
        r = ai_help.chat(self.folder, "q", runner=run, exe="/bin/claude")
        self.assertIn("rate limited", r["reply"])
        self.assertIsNone(ai_help._session(self.folder))
        self.assertEqual(ai_help.load_chat(self.folder)[-1]["role"], "error")

    def test_progress_rides_with_the_turn_not_the_transcript(self):
        ai_help.chat(self.folder, "next?", runner=self.runner(), exe="/bin/claude",
                     progress={"done": ["step one"]})
        self.assertIn("done so far: step one", self.calls[0][0][2])
        self.assertEqual(ai_help.load_chat(self.folder)[0]["text"], "next?")

    def test_timeout_is_a_reply(self):
        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 1)
        r = ai_help.chat(self.folder, "q", runner=slow, exe="/bin/claude")
        self.assertIn("too long", r["reply"])

    def test_no_claude_installed(self):
        r = ai_help.chat(self.folder, "q", runner=self.runner(), exe=None)
        self.assertIn("claude", r["reply"].lower())
        self.assertEqual(self.calls, [])

    def test_terminal_resumes_the_same_conversation(self):
        ai_help.chat(self.folder, "q", runner=self.runner(sid="s-9"), exe="/bin/claude")
        script = ai_help.terminal_command(self.folder, "/bin/claude")
        self.assertIn("cd '%s'" % self.folder, script)
        self.assertIn("exec '/bin/claude' --resume 's-9'", script)

    def test_terminal_without_a_panel_chat_starts_by_reading_the_context(self):
        script = ai_help.terminal_command(self.folder, "/bin/claude")
        self.assertNotIn("--resume", script)
        self.assertIn("Read CONTEXT.md", script)
        self.assertTrue(script.startswith("#!/bin/zsh"))

    def test_open_terminal_opens_the_launcher_and_reports_failure(self):
        calls = []
        ok = ai_help.open_terminal(self.folder, "/bin/claude", runner=lambda c, **k: calls.append(c) or Done("", 0))
        launcher = os.path.join(self.folder, ai_help.LAUNCHER)
        self.assertTrue(ok["ok"])
        self.assertEqual(calls[0], ["open", "-a", "Terminal", launcher])
        self.assertTrue(os.access(launcher, os.X_OK))
        bad = ai_help.open_terminal(self.folder, "/bin/claude", runner=lambda c, **k: Done("", 1, "no Terminal"))
        self.assertFalse(bad["ok"])
        self.assertIn("no Terminal", bad["error"])


class FailedRunMessageTests(unittest.TestCase):
    def test_failed_json_run_shows_its_readable_result(self):
        import types
        out = json.dumps({"is_error": True, "result": "You've hit your monthly spend limit", "usage": {"x": 1}})
        runner = lambda *a, **k: types.SimpleNamespace(returncode=1, stdout=out, stderr="")
        with tempfile.TemporaryDirectory() as folder:
            reply, sid = ai_help._ask(folder, "hi", runner, "/mock/claude")
        self.assertEqual(reply, "Claude hit an error: You've hit your monthly spend limit")
        self.assertIsNone(sid)


if __name__ == "__main__":
    unittest.main()
