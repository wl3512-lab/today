"""today_profile: one person's settings over generic defaults."""
import json
import os
import tempfile
import unittest

import today_profile as prof


class ProfileTest(unittest.TestCase):
    def test_defaults_without_a_file(self):
        p = prof.load("/nonexistent/profile.json")
        self.assertEqual(p["name"], "you")
        self.assertEqual(p["lms"]["kind"], "brightspace")
        self.assertEqual(p["studyWindow"]["start"], 10)

    def test_file_values_win_and_nested_defaults_stay(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"name": "Sam", "lms": {"host": "canvas.state.edu", "kind": "canvas"}}, fh)
        p = prof.load(fh.name)
        os.unlink(fh.name)
        self.assertEqual((p["name"], p["lms"]["host"], p["lms"]["kind"]), ("Sam", "canvas.state.edu", "canvas"))
        self.assertEqual(p["studyWindow"]["end"], 22)
        self.assertEqual(p["lms"]["sso"], "your school's sign-in")

    def test_course_url_for_each_platform(self):
        p = prof.load("/nonexistent")
        p["lms"]["host"] = "brightspace.example.edu"
        self.assertEqual(prof.lms_course_url(p, "123"), "https://brightspace.example.edu/d2l/le/content/123/Home")
        p["lms"].update(kind="canvas", host="canvas.example.edu")
        self.assertEqual(prof.lms_course_url(p, "77"), "https://canvas.example.edu/courses/77")

    def test_public_profile_hides_private_fields(self):
        p = prof.load("/nonexistent")
        p["discordName"] = "x"
        self.assertNotIn("discordName", prof.public(p))
        self.assertIn("lms", prof.public(p))

    def test_a_broken_file_falls_back_to_defaults(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
        p = prof.load(fh.name)
        os.unlink(fh.name)
        self.assertEqual(p["name"], "you")


if __name__ == "__main__":
    unittest.main()
