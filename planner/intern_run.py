"""Start the daily internship run from the planner, and say whether it is going.

The run itself lives in run-scout.sh behind the LaunchAgent that fires it each
morning. The button asks launchd to start that same job now rather than spawning
the script itself: one way to run means one environment (launchd's PATH, its
log, its working directory), and launchd will not start a second copy while
one is running - `kickstart` without -k leaves a live run alone.

The job's label, the morning prompt and the planner's own label come from the
profile (internships.scoutLabel, internships.dailyPrompt, launchLabel);
`python3 intern_run.py env|prompt` hands them to run-scout.sh.
"""
import os
import shlex
import subprocess
import sys
import time

import agent_path
from today_profile import PROFILE, planner_path

_started_at = None


def label(p=None):
    return ((p if p is not None else PROFILE).get("internships") or {}).get("scoutLabel") or "today.internscout"


LABEL = label()


def daily_prompt(p=None, agent=None):
    """The morning run's instructions for the agent: the shared ones, or the profile's own file."""
    p = p if p is not None else PROFILE
    with open(planner_path((p.get("internships") or {}).get("dailyPrompt") or "internship_daily_prompt.md")) as fh:
        text = fh.read()
    return text.format(agent=agent or agent_path.SCRIPTS, name=p.get("name") or "the student")


def shell_env(p=None, repo=None):
    p = p if p is not None else PROFILE
    return "\n".join("%s=%s" % (k, shlex.quote(v)) for k, v in (
        ("AGENT_REPO", repo or agent_path.REPO),
        ("PLANNER_LABEL", p.get("launchLabel") or "today.planner")))


def _target():
    return "gui/%d/%s" % (os.getuid(), LABEL)


def status(_body=None, runner=subprocess.run):
    try:
        p = runner(["launchctl", "print", _target()], capture_output=True, text=True, timeout=10)
        out = p.stdout if p.returncode == 0 else ""
    except Exception:
        out = ""
    running = "\tstate = running" in out
    return {"running": running, "startedAt": _started_at if running else None, "installed": bool(out)}


def start(_body=None, runner=subprocess.run):
    global _started_at
    now = status(runner=runner)
    if now["running"]:
        return dict(now, already=True)
    if not now["installed"]:
        return {"running": False, "error": "the internship job isn't installed (%s)" % LABEL}
    runner(["launchctl", "kickstart", _target()], capture_output=True, text=True, timeout=10)
    _started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    return {"running": True, "startedAt": _started_at, "already": False}


def handle(body, runner=subprocess.run):
    if (body or {}).get("action") == "start":
        return start(body, runner=runner)
    return status(body, runner=runner)


if __name__ == "__main__":       # run-scout.sh: eval "$(python3 intern_run.py env)"; python3 intern_run.py prompt
    sys.stdout.write(daily_prompt() if sys.argv[1:2] == ["prompt"] else shell_env() + "\n")
