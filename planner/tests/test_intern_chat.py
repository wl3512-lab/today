"""The résumé chat: rules about this student (not anyone in the code), its workspace, its command, its downloads."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("INTERNSHIP_AGENT_HOME", tempfile.mkdtemp(prefix="today-test-agent-"))
PLANNER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLANNER)
import agent_path  # noqa: E402

HAVE_AGENT = os.path.isdir(agent_path.SCRIPTS)
if HAVE_AGENT:
    import intern_chat as ic


class Done:
    def __init__(self, out, code=0):
        self.stdout, self.returncode, self.stderr = out, code, "boom"


@unittest.skipUnless(HAVE_AGENT, "no internship agent clone on this machine")
class RulesTests(unittest.TestCase):
    SAM = {"name": "Sam", "fullName": "Sam Rivera",
           "internships": {"facts": "BS Chemistry at State U, class of 2028.",
                           "extraRules": ["Never mention the robotics club: it folded."]}}

    def test_the_shared_rules_are_about_this_student(self):
        md = ic.claude_md(self.SAM, [{"group": "home"}, {"group": "state"}])
        self.assertIn("You help Sam tailor their résumé", md)
        self.assertIn("- Their facts: BS Chemistry at State U, class of 2028.\n"
                      "- Never mention the robotics club: it folded.\n- Never submit", md)
        self.assertIn("home/state/remote_global/remote_us/us/other", md)
        self.assertIn("python3 %s/intern_render.py" % ic.PLANNER, md)
        self.assertIsNone(re.search(r"\b(she|her|hers|he|him|his)\b", md))      # the student is "they"
        self.assertNotIn("{", md)

    def test_no_facts_means_only_what_the_resume_says(self):
        md = ic.claude_md({"name": "Sam"}, [])
        self.assertIn("- Their facts: only what `resumes/` says", md)
        self.assertIn("Their facts: only what `resumes/` says. Ask before assuming anything else"
                      " (a GPA, a visa, a graduation date).\n- Never submit", md)

    def test_a_rules_file_of_their_own(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        f = os.path.join(d, "rules.md")
        open(f, "w").write("You help {name}. Scripts in {planner}.")
        md = ic.claude_md({"name": "Sam", "internships": {"chatRules": f}}, [])
        self.assertEqual(md, "You help Sam. Scripts in %s." % ic.PLANNER)

    def test_a_relative_rules_file_sits_beside_the_planner(self):
        self.assertEqual(ic.rules_path({"internships": {"chatRules": "personal/x.md"}}),
                         os.path.join(PLANNER, "personal", "x.md"))


@unittest.skipUnless(HAVE_AGENT, "no internship agent clone on this machine")
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.prof = os.path.join(self.root, "profile.json")
        json.dump({"resume_text": "Sam Rivera\nGPA 3.4", "cv_text": "CV body", "cover_letter_text": "Dear team"},
                  open(self.prof, "w"))

    def test_the_library_holds_their_three_documents(self):
        names = ic.build_library(self.root, self.prof, {"fullName": "Sam Rivera"})
        self.assertEqual(sorted(names), ["sam-rivera-cover-letter.md", "sam-rivera-cv.md", "sam-rivera-resume.md"])
        self.assertIn("GPA 3.4", open(os.path.join(self.root, "resumes", "sam-rivera-resume.md")).read())

    def test_no_name_still_names_the_files(self):
        self.assertIn("student-resume.md", ic.build_library(self.root, self.prof, {"name": "", "fullName": ""}))

    def test_context_lists_only_open_postings_ready_first(self):
        data = {"postings": [
            {"id": "a", "company": "Sent Co", "role": "R", "status": "submitted"},
            {"id": "b", "company": "New Co", "role": "R", "status": "new", "fit": 5},
            {"id": "c", "company": "Ready Co", "role": "R", "status": "ready", "fit": 3}]}
        md = ic.context_md(data)
        self.assertNotIn("Sent Co", md)
        self.assertLess(md.index("Ready Co"), md.index("New Co"))


@unittest.skipUnless(HAVE_AGENT, "no internship agent clone on this machine")
class CommandTests(unittest.TestCase):
    def test_bash_is_only_the_five_scripts(self):
        allowed = ic.allowed_tools("/p")
        bash = [t for t in allowed.split(",") if t.startswith("Bash")]
        self.assertEqual(len(bash), 5)
        self.assertTrue(all(t.startswith("Bash(python3 /p/") for t in bash))
        self.assertNotIn("Bash,", allowed + ",")          # never bare Bash

    def test_command_resumes_and_never_skips_permissions(self):
        cmd = ic.command("hi", "/bin/claude", "s-1", "/p")
        self.assertEqual(cmd[cmd.index("--resume") + 1], "s-1")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], ic.DRAFTS)


@unittest.skipUnless(HAVE_AGENT, "no internship agent clone on this machine")
class ChatAndFilesTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.drafts = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.drafts, "acme-intern"))
        self._drafts = ic.DRAFTS
        ic.DRAFTS = self.drafts

    def tearDown(self):
        ic.DRAFTS = self._drafts
        shutil.rmtree(self.root)
        shutil.rmtree(self.drafts)

    def test_pdfs_written_during_the_turn_come_back_as_downloads(self):
        old = os.path.join(self.drafts, "acme-intern", "cover-letter.pdf")
        open(old, "w").write("old")
        os.utime(old, (1, 1))

        def run(cmd, **kw):
            open(os.path.join(self.drafts, "acme-intern", "resume.pdf"), "w").write("new")
            open(os.path.join(self.drafts, "acme-intern", "resume.prev.pdf"), "w").write("prev")
            return Done(json.dumps({"result": "Done - one page.", "session_id": "s1"}))
        out = ic.chat("tailor ACME", self.root, runner=run, exe="/bin/claude")
        self.assertEqual([f["path"] for f in out["files"]], ["acme-intern/resume.pdf"])
        self.assertEqual(ic.ai_help.load_chat(self.root)[-1]["files"][0]["name"], "resume.pdf")

    def test_an_error_turn_saves_no_session(self):
        out = ic.chat("x", self.root, runner=lambda c, **k: Done("", 1), exe="/bin/claude")
        self.assertIn("error", out["reply"])
        self.assertIsNone(ic.ai_help._session(self.root))

    def test_reset_starts_a_new_conversation(self):
        ic.chat("x", self.root, runner=lambda c, **k: Done(json.dumps({"result": "y", "session_id": "s"})),
                exe="/bin/claude")
        ic.reset(self.root)
        self.assertEqual(ic.ai_help.load_chat(self.root), [])
        self.assertIsNone(ic.ai_help._session(self.root))

    def test_downloads_stay_inside_the_drafts_folder(self):
        open(os.path.join(self.drafts, "acme-intern", "resume.pdf"), "w").write("x")
        self.assertTrue(ic.safe_file("acme-intern/resume.pdf", self.drafts))
        self.assertIsNone(ic.safe_file("../../.ssh/id_rsa", self.drafts))
        self.assertIsNone(ic.safe_file("acme-intern/../../etc/passwd", self.drafts))
        self.assertIsNone(ic.safe_file("acme-intern/secret.json", self.drafts))


if __name__ == "__main__":
    unittest.main()
