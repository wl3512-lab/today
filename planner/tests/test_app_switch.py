import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

class PlannerSwitchTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name in ("planner.html", "planner-next.html"):
            open(os.path.join(self.dir, name), "w").close()

    def test_defaults_to_the_full_planner(self):
        # planner-next.html only has Study on it until the other surfaces are
        # rebuilt, so the default stays on the planner that has everything.
        self.assertTrue(app.planner_path(app_dir=self.dir).endswith("/planner.html"))

    def test_a_page_file_opts_in(self):
        # The real switch: `open` strips the environment, so a file is the only
        # thing that survives the way the menubar is actually launched.
        with open(os.path.join(self.dir, app.PAGE_FILE), "w") as fh:
            fh.write("planner-next.html\n")
        self.assertTrue(app.planner_path(app_dir=self.dir).endswith("planner-next.html"))

    def test_an_empty_page_file_is_ignored(self):
        with open(os.path.join(self.dir, app.PAGE_FILE), "w") as fh:
            fh.write("   \n")
        self.assertTrue(app.planner_path(app_dir=self.dir).endswith("/planner.html"))

    def test_env_var_opts_in_to_the_rebuild(self):
        self.assertTrue(
            app.planner_path("planner-next.html", self.dir).endswith("planner-next.html"))

    def test_a_missing_build_falls_back_rather_than_opening_nothing(self):
        os.unlink(os.path.join(self.dir, "planner-next.html"))
        self.assertTrue(
            app.planner_path("planner-next.html", self.dir).endswith("/planner.html"))

if __name__ == "__main__":
    unittest.main()


from unittest.mock import patch


class OpenPlannerReusesWindowTests(unittest.TestCase):
    """Every press of Open Planner used to leave another window behind."""

    def test_an_open_planner_is_raised_not_reopened(self):
        with patch.object(app, "_planner_browser_pid", return_value=42), \
             patch.object(app, "_planner_windows", return_value=(1, 1)), \
             patch.object(app, "_activate", return_value=True) as act, \
             patch.object(app.subprocess, "Popen") as popen:
            app.open_in_browser()
        act.assert_called_once_with(42)
        popen.assert_not_called()

    def test_no_planner_running_opens_one(self):
        with patch.object(app, "_planner_browser_pid", return_value=None), \
             patch.object(app, "_activate") as act, \
             patch.object(app.subprocess, "Popen") as popen:
            app.open_in_browser()
        act.assert_not_called()
        self.assertEqual(popen.call_count, 1)

    def test_chrome_alive_with_every_window_closed_opens_one(self):
        # macOS keeps Chrome running after its last window closes; activating
        # it then would show nothing at all
        with patch.object(app, "_planner_browser_pid", return_value=42), \
             patch.object(app, "_planner_windows", return_value=(0, 0)), \
             patch.object(app, "_activate") as act, \
             patch.object(app.subprocess, "Popen") as popen:
            app.open_in_browser()
        act.assert_not_called()
        self.assertEqual(popen.call_count, 1)


    def test_a_minimized_planner_is_reopened_not_just_activated(self):
        # Activating Chrome does not un-minimize its window, so Open Planner
        # did nothing visible. Quit that instance and open a fresh window.
        with patch.object(app, "_planner_browser_pid", return_value=42), \
             patch.object(app, "_planner_windows", return_value=(1, 0)), \
             patch.object(app, "_quit_browser", return_value=True) as quit_, \
             patch.object(app, "_activate") as act, \
             patch.object(app.subprocess, "Popen") as popen:
            app.open_in_browser()
        quit_.assert_called_once_with(42)
        act.assert_not_called()
        self.assertEqual(popen.call_count, 1)

    def test_a_visible_window_that_will_not_activate_still_opens_one(self):
        with patch.object(app, "_planner_browser_pid", return_value=42), \
             patch.object(app, "_planner_windows", return_value=(1, 1)), \
             patch.object(app, "_activate", return_value=False), \
             patch.object(app.subprocess, "Popen") as popen:
            app.open_in_browser()
        self.assertEqual(popen.call_count, 1)
