"""Who this Today belongs to: name, school, platforms, study hours.

Read from ~/.today/profile.json (TODAY_PROFILE overrides the path) over the
generic defaults below, so the code itself holds nothing about one person or
one school. A missing or broken file means the defaults: the planner must
still open.
"""
import copy
import json
import os

PATH = os.path.expanduser(os.environ.get("TODAY_PROFILE", "~/.today/profile.json"))

DEFAULTS = {
    "name": "you",
    "fullName": "",
    "school": "",
    "timezone": "America/New_York",
    "lms": {"kind": "brightspace", "host": "", "sso": "your school's sign-in"},
    "notesUrl": "",
    "discordName": "",
    "githubWikiName": "",
    "publicHosts": [],
    "coursesPath": "~/.courses.json",
    "plugins": [],
    "features": [],
    # how prompts describe the student, and how the Ask chatbot answers
    "learner": "a student",
    "aiProxyUrl": "",
    "chatStyle": "Answer short and plain (under 150 words unless they ask for more), one idea at a time, with a concrete example from their screen when it helps.",
    "studyWindow": {"start": 10, "end": 22, "classPad": 30, "busyPad": 15,
                    "sessionMin": 60, "maxSessions": 8, "minStepMin": 30},
    # an empty dir means the quiz-prep folder beside the planner in this checkout
    "quizPrep": {"dir": "", "courses": []},
    # the planner's own LaunchAgent (the morning internship run restarts it after an agent update)
    "launchLabel": "today.planner",
    # the internship agent (feature "internships"); relative files sit beside the planner
    "internships": {"scoutLabel": "today.internscout", "chatRules": "internship_chat_rules.md",
                    "dailyPrompt": "internship_daily_prompt.md", "masterResume": "",
                    "tailorSkill": "~/claude-repos/resume-tailoring-skill", "facts": "", "extraRules": []},
}

# What the planner page may see: no handles, links or plugin names.
PUBLIC_KEYS = ("name", "school", "timezone", "lms", "studyWindow", "quizPrep", "features")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path=PATH):
    try:
        with open(path) as fh:
            return _merge(DEFAULTS, json.load(fh))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def public(p):
    return {k: p[k] for k in PUBLIC_KEYS if k in p}


def planner_path(value):
    """A file named in the profile: ~ expanded, and a relative name taken from the planner's folder."""
    path = os.path.expanduser(value or "")
    return path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.abspath(__file__)), path)


def lms_course_url(p, org_id):
    """A course's home page on the school's learning platform."""
    host = p["lms"]["host"]
    if p["lms"]["kind"] == "canvas":
        return "https://%s/courses/%s" % (host, org_id)
    return "https://%s/d2l/le/content/%s/Home" % (host, org_id)


PROFILE = load()
