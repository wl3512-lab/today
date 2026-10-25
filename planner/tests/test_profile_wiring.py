"""The planner reads school, names and hosts from the profile, not from its code."""
import unittest

import today_profile as prof
import kit
import assignment_context as ac
import ai_help
import discord_digest


class Wiring(unittest.TestCase):
    def setUp(self):
        self.p = prof.load("/nonexistent")
        self.p.update(name="Sam", discordName="sam1", publicHosts=["profsite.org"])
        self.p["lms"]["host"] = "learn.state.edu"

    def test_kit_knows_the_school_platform(self):
        self.assertTrue(kit.is_brightspace("https://learn.state.edu/d2l/home", self.p))
        self.assertFalse(kit.is_brightspace("https://brightspace.other.edu/d2l/home", self.p))
        self.assertFalse(kit.is_brightspace("https://x.edu/", prof.load("/nonexistent")), "no host set: nothing matches")

    def test_public_hosts_come_from_the_profile(self):
        self.assertTrue(ac.is_public("https://profsite.org/week3", self.p))
        self.assertTrue(ac.is_public("https://github.com/a/b", self.p))
        self.assertFalse(ac.is_public("https://learn.state.edu/x", self.p))

    def test_helper_names_the_student(self):
        text = ai_help.claude_md(self.p)
        self.assertIn("Helping Sam with this assignment", text)
        self.assertNotIn("{name}", text)

    def test_discord_prompt_names_the_student(self):
        text = discord_digest.make_prompt("a: hi", self.p)
        self.assertIn("Sam (Discord name sam1)", text)
        self.assertIn("a: hi", text)


if __name__ == "__main__":
    unittest.main()
