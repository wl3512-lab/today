# Today

A planner that lives in your Mac's menu bar and already knows your classes.
It pulls deadlines from your school's platform, class sites and GitHub, writes
a short brief for each assignment (what it is, the steps, how long each takes),
places study sessions around your classes and calendar, and opens everything
you need when you press start. Quiz Prep, which comes with it, builds a study
kit for each quiz from your own lecture slides.

A student built it for her own classes. Claude adapts it to yours.

## Get it

You need a Mac and [Claude Code](https://claude.com/claude-code). Open Claude
Code in your home folder and paste:

```
Set up Today for me: clone https://github.com/wl3512-lab/today into ~/today,
then read CLAUDE-SETUP.md there and follow it.
```

Claude asks you about your classes (drop in your syllabi and it reads them),
what each class needs, and when you like to study. Then it writes your
settings, installs the app and checks that it works with you. Plan on about 15
minutes and keep your school sign-in handy.

Your settings stay on your Mac in `~/.today/profile.json` and
`~/.courses.json`. Today only talks to the places you give it during setup
(your school's platform, class sites, GitHub, your calendar link) and to
Claude when it writes a brief.

## What you get

**Today page.** Your next class and when to leave, what's due soonest, and
what to start thinking about now.

**Homework pages.** Tap a deadline for its brief, every link that goes with it,
and **Plan it**, which places work sessions around your classes and calendar
events. Move a session by tapping it.

**Study Kit.** Press start on an assignment: its links, notes and apps open,
your Study Focus turns on, your playlist opens in a tab, and a 25/5 timer starts
once you tick the "desk ready" checklist. Logged minutes add up per assignment and per
class.

**Classes.** Per class: meeting times, office hours, recent announcements, new
files in the class repo, your running grade from posted scores and the
syllabus weights, and absences against the attendance rule.

**Quiz Prep** (for quiz and exam classes). A kit for the next quiz from your
slides: review, formulas, flashcards, a fresh worksheet with checked answers,
and a practice test. You can also photograph a past quiz to get new practice
in the same format. The AI writes the words; code computes every number.

## Works with

| | |
|---|---|
| School platforms | Brightspace (any school), Canvas. Claude can write a connector for Moodle or Blackboard during setup. |
| Also reads | class websites, GitHub repos and wikis, published Google Docs and Sheets, Campuswire, Google Calendar (iCal link), Gmail (optional) |
| Needs | macOS, Python 3.9+ from python.org or Homebrew, Claude Code. Node.js 18+ for Quiz Prep. |

## Update

Ask Claude: "update Today". It follows `CLAUDE-UPDATE.md`: shows what
changed, pulls, runs the tests and restarts. Your settings and history stay.

## Remove

`tools/uninstall.sh --yes` stops the app and removes its background jobs.
Your settings and study history stay until you delete them.

## Folders

| folder | what |
|---|---|
| `planner/` | the menu bar app, its page (`planner.html`) and the class sync |
| `quiz-prep/` | Quiz Prep (Node, runs on localhost:3123) |
| `connectors/` | Brightspace, Canvas and Campuswire readers |
| `recipes/` | how setup handles each kind of class |
| `templates/` | example settings and the field reference |
| `tools/` | install, uninstall, doctor (health check), privacy scan |

The optional internship search lives in its own repo,
[internship-agent](https://github.com/wl3512-lab/internship-agent).

MIT license. See `NOTICE.md` for third-party parts.
