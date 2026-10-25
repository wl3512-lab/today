"""The internship agent as a core feature: on only when the profile asks for it, keyed where it runs agents."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

os.environ.setdefault("INTERNSHIP_AGENT_HOME", tempfile.mkdtemp(prefix="today-test-agent-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_path  # noqa: E402
import plugins  # noqa: E402

HAVE_AGENT = os.path.isdir(agent_path.SCRIPTS)


class FeatureTests(unittest.TestCase):
    def test_the_feature_brings_its_plugin(self):
        self.assertEqual(plugins.names_for({"plugins": ["mine"], "features": ["internships"]}),
                         ["mine", "internships_plugin"])

    def test_no_feature_no_plugin(self):
        self.assertEqual(plugins.names_for({"plugins": [], "features": ["cravings"]}), [])

    def test_listed_once(self):
        self.assertEqual(plugins.names_for({"plugins": ["internships_plugin"], "features": ["internships"]}),
                         ["internships_plugin"])


class AgentPathTests(unittest.TestCase):
    def folder(self, scripts=True):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        if scripts:
            os.makedirs(os.path.join(d, "scripts"))
        return d

    def test_the_environment_wins(self):
        d = self.folder()
        self.assertEqual(agent_path.find(env=d), os.path.realpath(d))

    def test_beside_the_planner_before_home(self):
        a, b = self.folder(), self.folder()
        self.assertEqual(agent_path.find(env="", candidates=(a, b)), os.path.realpath(a))

    def test_skips_a_folder_without_scripts(self):
        a, b = self.folder(scripts=False), self.folder()
        self.assertEqual(agent_path.find(env="", candidates=(a, b)), os.path.realpath(b))

    def test_a_link_resolves_to_the_real_folder(self):
        # the planner window grants file reads by folder, and WebKit follows links
        real = self.folder()
        link = real + "-link"
        os.symlink(real, link)
        self.addCleanup(os.remove, link)
        self.assertEqual(agent_path.find(env="", candidates=(link,)), os.path.realpath(real))


@unittest.skipUnless(HAVE_AGENT, "no internship agent clone on this machine")
class PluginTests(unittest.TestCase):
    def setUp(self):
        plugins.load(["internships_plugin"])
        self.mod = plugins.get("internships_plugin")
        self.assertIsNotNone(self.mod, "internships_plugin did not load")
        self.addCleanup(plugins._loaded.pop, "internships_plugin", None)

    def test_routes_are_registered(self):
        routes = plugins.post_routes()
        for path in ("/internships", "/internships/open", "/internships/fill", "/internships/fill/show",
                     "/internships/run", "/internships/chat/open", "/internships/chat", "/internships/chat/reset"):
            self.assertIn(path, routes)

    def test_agent_routes_need_the_key(self):
        self.assertIn("/internships/run", plugins.keyed_routes())
        self.assertIn("/internships/chat", plugins.keyed_routes())

    def test_the_window_may_read_the_agent_clone(self):
        self.assertIn(agent_path.REPO, plugins.read_roots())

    def test_the_page_gets_the_students_places_in_their_order(self):
        prof = {"places": [{"group": "home", "label": "Springfield", "match": ["springfield"]},
                           {"group": "state", "label": "Elsewhere in Ohio", "match": ["ohio"]},
                           {"group": "broken"}]}
        data = self.mod.page_data(prof)
        self.assertEqual(data["places"], [{"group": "home", "label": "Springfield"},
                                          {"group": "state", "label": "Elsewhere in Ohio"}])
        self.assertIn("postings", data)

    def test_downloads_are_named_for_the_student_and_the_job(self):
        name = self.mod.download_name
        self.assertEqual(name("/d/acme-design-intern/resume.pdf", {"fullName": "Test Student"}),
                         "Test_Student_acme-design-intern_resume.pdf")
        self.assertEqual(name("/d/acme/cover-letter.pdf", {"fullName": ""}), "Resume_acme_cover-letter.pdf")
        self.assertEqual(name("/d/acme/notes.md", {"fullName": "Test Student"}), "notes.md")


@unittest.skipUnless(HAVE_AGENT, "no internship agent clone on this machine")
class ServerTests(unittest.TestCase):
    def setUp(self):
        plugins.load(["internships_plugin"])
        self.addCleanup(plugins._loaded.pop, "internships_plugin", None)
        import state_server
        kick = state_server.GCAL.kick
        state_server.GCAL.kick = lambda: None
        self.addCleanup(setattr, state_server.GCAL, "kick", kick)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.srv, _ = state_server.start_server(os.path.join(self.dir, "state.json"), port=0)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.srv.server_address[1], path)

    def test_agent_and_resume_chat_refuse_without_the_key(self):
        for path in ("/internships/run", "/internships/chat", "/internships/chat/open", "/internships/chat/reset"):
            req = urllib.request.Request(self.url(path), data=json.dumps({"token": "guess"}).encode(),
                                         method="POST", headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 403, path)

    def test_draft_download_needs_the_key(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url("/internships/file?path=x/resume.pdf&token=guess"), timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_the_page_list_answers(self):
        with urllib.request.urlopen(self.url("/internships"), timeout=5) as r:
            data = json.loads(r.read())
        self.assertIn("postings", data)
        self.assertIn("places", data)


if __name__ == "__main__":
    unittest.main()
