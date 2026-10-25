"""A different student (Sam, Canvas at State U, chemistry): the core speaks to Sam, never to this Mac's owner."""
import json
import os
import unittest

import today_profile as prof
import kit
import ai_help
import discord_digest
import assignment_context as ac

SAM = prof.load(os.path.join(os.path.dirname(__file__), "fixtures", "sam-profile.json"))
OWNER = prof.load(os.path.expanduser("~/.today/profile.json"))   # defaults when this Mac has no owner settings
OWNER_MARKS = [w for w in (OWNER["name"], OWNER["fullName"], OWNER["discordName"], OWNER["lms"]["host"], OWNER["notesUrl"],
                           OWNER["learner"] if OWNER["learner"] != "a student" else "")
               if w and len(w) > 3 and w not in ("you",)] + list(((OWNER.get("quizPrep") or {}).get("settings") or {}).keys())


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from strings(v)


class SecondStudentTest(unittest.TestCase):
    def assertNoOwner(self, *outputs):
        for text in strings(list(outputs)):
            for mark in OWNER_MARKS:
                self.assertNotIn(mark, text, "%r leaked into %r" % (mark, text[:120]))

    def test_canvas_course_pages(self):
        self.assertEqual(prof.lms_course_url(SAM, "4411"), "https://canvas.stateu.edu/courses/4411")
        self.assertTrue(kit.is_brightspace("https://canvas.stateu.edu/courses/4411", SAM), "the school platform is recognised")

    def test_public_profile_and_prompts_are_about_sam(self):
        out = [prof.public(SAM), ai_help.claude_md(SAM), discord_digest.make_prompt("a: hi", SAM)]
        self.assertIn("Helping Sam", out[1])
        self.assertNoOwner(*out)

    def test_course_sites(self):
        self.assertTrue(ac.is_public("https://chem.stateu.edu/week2", SAM))
        for host in OWNER["publicHosts"]:
            self.assertFalse(ac.is_public("https://%s/x" % host, SAM), "another student's class sites are not Sam's")


if __name__ == "__main__":
    unittest.main()
