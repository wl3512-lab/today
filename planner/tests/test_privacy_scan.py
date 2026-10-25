"""Nothing personal in the files git would publish (the owner's words come from ~/.today/profile.json when present)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import privacy_scan  # noqa: E402


class PrivacyScanTest(unittest.TestCase):
    def test_finds_planted_secrets(self):
        hits = privacy_scan.scan(files=["planner/tests/fixtures/profile-test.json"],
                                 patterns=[r"notes\.example\.com"])
        self.assertTrue(hits, "the scanner sees a planted pattern")

    def test_the_repo_is_clean(self):
        hits = privacy_scan.scan(patterns=privacy_scan.BUILTIN + privacy_scan.owner_words("~/.today/profile.json"))
        self.assertEqual(hits, [], "\n".join("%s:%d [%s] %s" % h for h in hits[:20]))


if __name__ == "__main__":
    unittest.main()
