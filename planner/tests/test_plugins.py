"""Personal extras load as plugins named in the profile; the core runs the same without them."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

import plugins


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.addCleanup(plugins.reset)
        with open(os.path.join(self.dir, "fake_extra.py"), "w") as f:
            f.write(
                "POST_ROUTES = {'/extra/ping': lambda body: {'pong': body.get('n')}}\n"
                "def handle_get(h):\n"
                "    if h.path == '/extra/hello':\n"
                "        h._send_json({'hello': 'from a plugin'}); return True\n"
                "    return False\n"
                "def fetch_items(course, errors):\n"
                "    return [{'title': 'from plugin', 'courseKey': course.get('key')}]\n")
        self.addCleanup(lambda: sys.modules.pop("fake_extra", None))

    def test_loads_listed_plugins_and_skips_missing_ones(self):
        got = plugins.load(["fake_extra", "not_installed_anywhere"], search=[self.dir])
        self.assertIn("fake_extra", got)
        self.assertNotIn("not_installed_anywhere", got)
        self.assertIs(plugins.get("fake_extra"), got["fake_extra"])

    def test_merges_post_routes_and_course_items(self):
        plugins.load(["fake_extra"], search=[self.dir])
        self.assertEqual(plugins.post_routes()["/extra/ping"]({"n": 3}), {"pong": 3})
        self.assertEqual(plugins.course_items({"key": "c1"}, []), [{"title": "from plugin", "courseKey": "c1"}])

    def test_nothing_loaded_means_no_routes_and_no_items(self):
        self.assertEqual(plugins.post_routes(), {})
        self.assertEqual(plugins.course_items({"key": "c1"}, []), [])

    def test_server_serves_plugin_routes(self):
        import state_server
        plugins.load(["fake_extra"], search=[self.dir])
        kick = state_server.GCAL.kick
        state_server.GCAL.kick = lambda: None
        self.addCleanup(setattr, state_server.GCAL, "kick", kick)
        srv, _ = state_server.start_server(os.path.join(self.dir, "state.json"), port=0)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        with urllib.request.urlopen(base + "/extra/hello", timeout=5) as r:
            self.assertEqual(json.loads(r.read()), {"hello": "from a plugin"})
        req = urllib.request.Request(base + "/extra/ping", data=json.dumps({"n": 7}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(json.loads(r.read()), {"pong": 7})


if __name__ == "__main__":
    unittest.main()


class KeyedRouteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.addCleanup(plugins.reset)
        with open(os.path.join(self.dir, "keyed_extra.py"), "w") as f:
            f.write("POST_ROUTES = {'/agent/run': lambda b: {'ran': True}}\nKEYED_ROUTES = ('/agent/',)\n")
        self.addCleanup(lambda: sys.modules.pop("keyed_extra", None))

    def test_a_keyed_plugin_route_refuses_without_the_key(self):
        import state_server
        plugins.load(["keyed_extra"], search=[self.dir])
        self.assertEqual(plugins.keyed_routes(), ["/agent/"])
        kick = state_server.GCAL.kick
        state_server.GCAL.kick = lambda: None
        self.addCleanup(setattr, state_server.GCAL, "kick", kick)
        srv, _ = state_server.start_server(os.path.join(self.dir, "state.json"), port=0)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        req = urllib.request.Request("http://127.0.0.1:%d/agent/run" % srv.server_address[1], data=b"{}", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 403)
