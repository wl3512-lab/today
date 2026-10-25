import json, os, shutil, subprocess, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import planner_window as pw


class OpenPlannerUsesItsOwnWindowTests(unittest.TestCase):
    """The planner opened as a second Google Chrome, which took over the Dock icon."""

    def test_native_window_is_the_default(self):
        with patch.object(pw, "wanted", return_value=True), \
             patch.object(pw, "show") as show, \
             patch.object(app.subprocess, "Popen") as popen:
            app.open_as_app_window()
        show.assert_called_once_with(app.PLANNER_PATH)
        popen.assert_not_called()

    def test_asking_for_chrome_back_uses_the_browser(self):
        with patch.object(pw, "wanted", return_value=False), \
             patch.object(pw, "show") as show, \
             patch.object(app, "open_in_browser") as browser:
            app.open_as_app_window()
        show.assert_not_called()
        browser.assert_called_once_with()

    def test_a_failing_window_still_opens_the_planner(self):
        with patch.object(pw, "wanted", return_value=True), \
             patch.object(pw, "show", side_effect=RuntimeError("no WebKit")), \
             patch.object(app, "open_in_browser") as browser:
            app.open_as_app_window()
        browser.assert_called_once_with()

    def test_opt_out_file_turns_the_native_window_off(self):
        d = tempfile.mkdtemp()
        self.assertEqual(pw.wanted(d), pw.AVAILABLE)
        open(os.path.join(d, ".planner-in-chrome"), "w").close()
        self.assertFalse(pw.wanted(d))
        shutil.rmtree(d)


class ReadRootTests(unittest.TestCase):
    """WebKit only reads files under the root it is given; the Internships page
    loads its code from the agent's clone beside the planner."""

    def test_root_covers_the_planner_and_the_agent_clone(self):
        home = tempfile.mkdtemp()
        planner = os.path.join(home, "today-planner"); os.mkdir(planner)
        clone = os.path.join(home, "internship-agent"); os.mkdir(clone)
        root = pw.read_root(os.path.join(planner, "planner.html"), repo=clone)
        self.assertEqual(root, os.path.realpath(home) if root.startswith("/private") else home)
        shutil.rmtree(home)

    def test_no_clone_means_just_the_planner_folder(self):
        d = tempfile.mkdtemp()
        self.assertEqual(pw.read_root(os.path.join(d, "planner.html"), repo=os.path.join(d, "nope")), d)
        shutil.rmtree(d)

    def test_the_real_page_can_reach_the_internships_ui(self):
        import plugins
        plugins.load(["internships_plugin"])              # what the "internships" feature turns on
        self.addCleanup(plugins._loaded.pop, "internships_plugin", None)
        root = pw.read_root(app.PLANNER_PATH)
        ui = os.path.join(os.path.dirname(app.PLANNER_PATH), "..", "internship-agent", "ui", "internships.js")
        if os.path.exists(ui):
            self.assertTrue(os.path.abspath(ui).startswith(root + os.sep))


class LinksGoToHerBrowserTests(unittest.TestCase):
    def test_the_web_leaves(self):
        self.assertTrue(pw.goes_to_browser("https://brightspace.example.edu/d2l/home"))
        self.assertTrue(pw.goes_to_browser("http://127.0.0.1:8765/download.html"))
        self.assertTrue(pw.goes_to_browser("mailto:prof@example.edu"))

    def test_the_planner_and_local_pages_stay(self):
        self.assertFalse(pw.goes_to_browser("file:///Users/someone/today/planner/planner.html?v=1"))
        self.assertFalse(pw.goes_to_browser("about:blank"))
        self.assertFalse(pw.goes_to_browser("blob:file:///abc"))

    def test_frames_inside_the_page_stay(self):
        self.assertFalse(pw.goes_to_browser("https://www.youtube.com/embed/x", main_frame=False))


@unittest.skipUnless(shutil.which("node"), "node runs the migration script")
class MigrationRunsOnceTests(unittest.TestCase):
    """The old Chrome localStorage is copied in once and never over newer values."""

    def run_js(self, script, before):
        harness = (
            "const store=new Map(Object.entries(%s));"
            "global.localStorage={getItem:k=>store.has(k)?store.get(k):null,"
            "setItem:(k,v)=>store.set(k,String(v)),get length(){return store.size}};"
            "%s;console.log(JSON.stringify(Object.fromEntries(store)));" % (json.dumps(before), script))
        out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_first_load_copies_everything_and_sets_the_flag(self):
        after = self.run_js(pw.migration_script({"today.steps": "[1]", "today-simple-v1": "{}"}), {})
        self.assertEqual(after["today.steps"], "[1]")
        self.assertEqual(after["today-simple-v1"], "{}")
        self.assertIn(pw.MIGRATED_FLAG, after)

    def test_a_second_load_never_overwrites_newer_values(self):
        before = {pw.MIGRATED_FLAG: "2026-10-07", "today.steps": "[2, 3]"}
        after = self.run_js(pw.migration_script({"today.steps": "[1]"}), before)
        self.assertEqual(after["today.steps"], "[2, 3]")


class LoadMigrationTests(unittest.TestCase):
    def test_missing_or_bad_file_is_none(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(pw.load_migration(os.path.join(d, "nope.json")))
        bad = os.path.join(d, "bad.json")
        open(bad, "w").write("not json")
        self.assertIsNone(pw.load_migration(bad))
        shutil.rmtree(d)

    def test_values_come_back_as_strings(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "ls.json")
        json.dump({"a": "1", "b": "x"}, open(p, "w"))
        self.assertEqual(pw.load_migration(p), {"a": "1", "b": "x"})
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
