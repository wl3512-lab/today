"""The Internships page's "Run now" button, and the settings the morning job reads from the profile."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import intern_run  # noqa: E402


class Done:
    def __init__(self, out="", code=0):
        self.stdout, self.returncode, self.stderr = out, code, ""


class SettingsTests(unittest.TestCase):
    def test_the_job_label_comes_from_the_profile(self):
        self.assertEqual(intern_run.label({"internships": {"scoutLabel": "edu.state.sam.scout"}}), "edu.state.sam.scout")
        self.assertEqual(intern_run.label({}), "today.internscout")

    def test_the_shared_morning_prompt(self):
        text = intern_run.daily_prompt({"name": "Sam"}, agent="/a/scripts")
        self.assertIn("`python3 /a/scripts/intern_agent.py notes --apply`", text)
        self.assertIn("morning run for Sam", text)
        self.assertIsNone(re.search(r"\b(she|her|hers|he|him|his)\b", text))
        self.assertNotIn("{", text)

    def test_the_shell_gets_the_agent_and_the_planner_label(self):
        env = intern_run.shell_env({"launchLabel": "edu.state.sam.today"}, repo="/r/internship agent")
        self.assertIn("AGENT_REPO='/r/internship agent'", env)
        self.assertIn("PLANNER_LABEL=edu.state.sam.today", env)
        self.assertIn("PLANNER_LABEL=today.planner", intern_run.shell_env({}, repo="/r"))


class RunTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        intern_run._started_at = None

    def runner(self, state):
        def run(cmd, **kw):
            self.calls.append(cmd)
            if cmd[1] == "print":
                return Done("\tstate = %s\n\tlast exit code = 0\n" % state)
            return Done()
        return run

    def test_start_kicks_the_launchd_job(self):
        out = intern_run.start({}, runner=self.runner("not running"))
        self.assertTrue(out["running"])
        kick = [c for c in self.calls if c[1] == "kickstart"][0]
        self.assertTrue(kick[2].endswith("/" + intern_run.LABEL))
        self.assertNotIn("-k", kick)               # never kill a run in progress

    def test_start_while_running_does_not_start_another(self):
        out = intern_run.start({}, runner=self.runner("running"))
        self.assertTrue(out["already"])
        self.assertFalse([c for c in self.calls if c[1] == "kickstart"])

    def test_status_reads_launchd(self):
        self.assertTrue(intern_run.status({}, runner=self.runner("running"))["running"])
        self.assertFalse(intern_run.status({}, runner=self.runner("not running"))["running"])

    def test_route_dispatches_on_action(self):
        r = self.runner("not running")
        self.assertFalse(intern_run.handle({"action": "status"}, runner=r)["running"])
        self.assertTrue(intern_run.handle({"action": "start"}, runner=r)["running"])


if __name__ == "__main__":
    unittest.main()
