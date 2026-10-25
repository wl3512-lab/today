"""Load the internship agent from its own clone, not from copies in here.

The agent (scout, mail scan, ranking, tailoring, form filling, the tracker) is
its own repo, github.com/wl3512-lab/internship-agent. The planner imports it
from a clone, so an update pulled from GitHub is the update the planner runs -
run-scout.sh pulls every morning. The clone is found at $INTERNSHIP_AGENT_REPO,
else beside the planner (<today>/internship-agent, where setup puts it), else
~/internship-agent. Its data lives in ~/.internship-agent/ (tracker.json,
profile.json, watchlist.json, applications/).

Import this before any of the agent's modules:  import agent_path  # noqa
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = (os.path.join(os.path.dirname(HERE), "internship-agent"), os.path.expanduser("~/internship-agent"))


def find(env=None, candidates=CANDIDATES):
    env = os.environ.get("INTERNSHIP_AGENT_REPO") if env is None else env
    if env:
        return os.path.realpath(os.path.expanduser(env))
    for c in candidates:
        if os.path.isdir(os.path.join(c, "scripts")):
            # the real folder: the planner window grants file reads by folder, and WebKit follows links
            return os.path.realpath(c)
    return os.path.realpath(candidates[0])


REPO = find()
SCRIPTS = os.path.join(REPO, "scripts")

if not os.path.isdir(SCRIPTS):
    sys.stderr.write("[agent_path] no internship agent at %s - clone "
                     "https://github.com/wl3512-lab/internship-agent there\n" % SCRIPTS)
elif SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
