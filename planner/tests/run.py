"""Run the planner's tests as a made-up student, not as whoever's settings are on this Mac.

    python3 tests/run.py            (all tests)
The owner's own settings are checked by planner/personal/tests (not part of the shared core).
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("TODAY_PROFILE", os.path.join(HERE, "fixtures", "profile-test.json"))
# the internship agent keeps its tracker and profile here; never the real ~/.internship-agent
os.environ.setdefault("INTERNSHIP_AGENT_HOME", tempfile.mkdtemp(prefix="today-test-agent-"))
sys.path.insert(0, os.path.dirname(HERE))
os.chdir(os.path.dirname(HERE))
suite = unittest.defaultTestLoader.discover(HERE, pattern="test_*.py", top_level_dir=HERE)
# the school-platform connectors ship beside the planner and are tested with it
CONNECTOR_TESTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "connectors", "tests")
if os.path.isdir(CONNECTOR_TESTS):
    suite.addTests(unittest.defaultTestLoader.discover(CONNECTOR_TESTS, pattern="test_*.py", top_level_dir=CONNECTOR_TESTS))
sys.exit(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
