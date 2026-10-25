"""One box per Discord server in the feed: what the conversation is about."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import discord_digest as dd

MSGS = [
    {"title": "#team-app · Robin/Kai: Im doing the settings screen", "at": "2026-09-28T00:36:44Z",
     "body": "Im doing the settings screen", "url": "https://discord.com/channels/1/2/3", "source": "discord"},
    {"title": "#team-app · @Robin/Kai: @tester1 I am just gonna start dropping in some screenshots", "at": "2026-09-27T23:52:06Z",
     "body": "@tester1 I am just gonna start dropping in some screenshots and start there. Which pages are you doing?",
     "url": "https://discord.com/channels/1/2/2", "source": "discord"},
    {"title": "#team-app · Morgan Lee: ^ figma file in the same folder", "at": "2026-09-27T22:30:00Z",
     "body": "^ figma file in the same folder, so we can stay organized.", "url": "https://discord.com/channels/1/2/1", "source": "discord"},
]


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.store = os.path.join(tempfile.mkdtemp(), "digests.json")
        self.prompts = []

    def ask(self, reply):
        def f(prompt):
            self.prompts.append(prompt)
            return reply
        return f

    def test_one_box_with_counts_channels_and_latest(self):
        d = dd.build("studio101", MSGS, path=self.store, ask=self.ask("You and Kai are splitting up the audit."))
        self.assertEqual(d["count"], 3)
        self.assertEqual(d["channels"], ["team-app"])
        self.assertEqual(d["people"], ["Robin/Kai", "Morgan Lee"])
        self.assertEqual(d["latestAt"], "2026-09-28T00:36:44Z")
        self.assertEqual(d["url"], "https://discord.com/channels/1/2/3")
        self.assertEqual(d["summary"], "You and Kai are splitting up the audit.")

    def test_prompt_carries_the_messages_oldest_first_and_names_her(self):
        dd.build("studio101", MSGS, path=self.store, ask=self.ask("x"))
        p = self.prompts[0]
        self.assertLess(p.index("figma file"), p.index("settings screen"))
        self.assertIn(dd.HER, p)   # the student's own Discord name, from the profile

    def test_same_messages_are_not_summarised_twice(self):
        dd.build("studio101", MSGS, path=self.store, ask=self.ask("first"))
        d = dd.build("studio101", MSGS, path=self.store, ask=self.ask("second"))
        self.assertEqual(d["summary"], "first")
        self.assertEqual(len(self.prompts), 1)

    def test_new_message_gets_a_new_summary(self):
        dd.build("studio101", MSGS[1:], path=self.store, ask=self.ask("first"))
        d = dd.build("studio101", MSGS, path=self.store, ask=self.ask("second"))
        self.assertEqual(d["summary"], "second")

    def test_no_model_falls_back_to_who_and_where_not_a_guess(self):
        d = dd.build("studio101", MSGS, path=self.store, ask=self.ask(""))
        self.assertEqual(d["summary"], "")
        self.assertIn("3 messages in #team-app from Robin/Kai and Morgan Lee", d["fallback"])
        # and an empty answer is not cached, so the next sync tries again
        d2 = dd.build("studio101", MSGS, path=self.store, ask=self.ask("now it works"))
        self.assertEqual(d2["summary"], "now it works")

    def test_no_messages_no_box(self):
        self.assertIsNone(dd.build("studio101", [], path=self.store, ask=self.ask("x")))


if __name__ == "__main__":
    unittest.main()
