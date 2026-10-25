"""/study hands the planner page the public part of the profile (school platform, study hours), never handles or links."""
import json
import os
import shutil
import tempfile
import unittest
import urllib.request

import state_server
from state_server import start_server


class StudyProfileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.cache = os.path.join(self.dir, "cache.json")
        with open(self.cache, "w") as f:
            json.dump({"courses": [{"key": "math101"}]}, f)
        orig = state_server.STUDY_CACHE
        self.addCleanup(setattr, state_server, "STUDY_CACHE", orig)
        state_server.STUDY_CACHE = self.cache
        kick = state_server.GCAL.kick
        state_server.GCAL.kick = lambda: None
        self.addCleanup(setattr, state_server.GCAL, "kick", kick)
        self.server, _ = start_server(os.path.join(self.dir, "state.json"), port=0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def study(self):
        url = "http://127.0.0.1:%d/study" % self.server.server_address[1]
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())

    def test_profile_rides_along_with_the_courses(self):
        data = self.study()
        self.assertEqual(data["courses"][0]["key"], "math101")
        self.assertEqual(data["profile"]["lms"]["host"], state_server.PROFILE["lms"]["host"])
        self.assertEqual(data["profile"]["studyWindow"]["start"], 10)
        for private in ("discordName", "notesUrl", "plugins", "githubWikiName", "publicHosts"):
            self.assertNotIn(private, data["profile"])

    def test_profile_is_there_even_without_course_data(self):
        os.remove(self.cache)
        data = self.study()
        self.assertEqual(data["courses"], [])
        self.assertIn("lms", data["profile"])


if __name__ == "__main__":
    unittest.main()
