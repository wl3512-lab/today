# Settings reference

Two files hold everything about one student. Neither is in the repo.

| file | what | written by |
|---|---|---|
| `~/.today/profile.json` | who you are, your school's platform, study hours, Quiz Prep courses | setup (`CLAUDE-SETUP.md`), from `profile.example.json` |
| `~/.courses.json` | your classes: when they meet, where their work lives, how they are graded | setup, from `courses.example.json` |

Missing fields fall back to defaults, so a short file is fine. A broken
file means defaults too: the planner still opens.

## profile.json

| field | meaning | example |
|---|---|---|
| `name` | what the planner and its AI helpers call you | `"Sam"` |
| `fullName` | used in downloaded file names | `"Sam Rivera"` |
| `school` | shown in prompts and sign-in messages | `"State University"` |
| `timezone` | IANA name | `"America/Chicago"` |
| `lms.kind` | `brightspace`, `canvas`, or anything else for none | `"canvas"` |
| `lms.host` | the platform's address, no `https://`. Empty = don't read a platform | `"canvas.stateu.edu"` |
| `lms.sso` | what your school calls its sign-in | `"State U sign-in"` |
| `notesUrl` | your notes page; the Study Kit opens it | Notion, Google Doc, ... |
| `githubWikiName` | your name as it appears on class wiki submission lists | `"srivera"` |
| `publicHosts` | class sites that need no login, so assignment pages can be read for briefs | `["chem.stateu.edu"]` |
| `coursesPath` | where the course file lives | `"~/.courses.json"` |
| `plugins` | Python modules in `~/.today/plugins/` for one-off class sites (see `planner/plugins.py`) | `[]` |
| `features` | extras to switch on: `"internships"` | `[]` |
| `learner` | how AI prompts describe you | `"a first-year student"` |
| `aiProxyUrl` | a class AI proxy, if your school gives you one. Empty = use Claude Code | `""` |
| `studyWindow` | when study sessions may be placed: `start`/`end` hour, minutes kept clear around classes (`classPad`) and calendar events (`busyPad`), session length, max sessions per assignment, shortest step | see the example |
| `quizPrep.courses` | course keys that get Quiz Prep | `["chem101"]` |
| `quizPrep.settings.<key>` | per quiz course: `subject` (`stats` turns on the z-test calculator and number banks, else `generic`), `title`, `professor`, `label`, `fileTag` (text in the slide file names), `lessonWord` (`Lesson`, `Chapter`, `Week`), `noCalculator`, `quizPoints`, and for stats `cutoffs` / `levels` | see the example |
| `quizPrep.dir` | where Quiz Prep lives; empty = `quiz-prep/` in this checkout | `""` |
| `launchLabel` | the planner's LaunchAgent label | `"today.planner"` |
| `syncLabel` | the course sync's LaunchAgent label; empty = `launchLabel` + `.sync` | `""` |

## courses.json

Top level:

| field | meaning |
|---|---|
| `term` | label only, e.g. `"Fall 2026"` |
| `studyPlaylist` | a web link the Study Kit opens in a tab (SoundCloud, YouTube, Spotify web) |
| `calendar.ics` | your calendar's secret iCal address, so study sessions avoid your events. Keep it secret: it is a password |
| `courses` | one entry per class (below) |
| `ignore` | platform courses to hide (`name`, `lmsId`, `why`) so old classes don't come back |

Each course. Only `key` and `name` are required; add what the syllabus actually says.

| field | meaning |
|---|---|
| `key` | short id, lowercase, no spaces: `chem101` |
| `name`, `short`, `code` | full name, tab label, catalog code |
| `lmsId` | the course's id on Brightspace or Canvas (the number in its URL). Ties platform deadlines to this class. `null` if it has none |
| `instructor`, `ta`, `officeHours` | shown on the class page |
| `meets` | `day`, `start`, `end` (24h), `room`. The planner shows when to leave and keeps study sessions off class time |
| `term` | `start`, `end` dates |
| `sources` | where the class's work lives (kinds below) |
| `grading`, `gradeScheme` | syllabus weights; `gradeScheme` adds `drops`, `scale`, `outOf`, `changes`. With platform grades the planner shows a running average |
| `attendance` | `allowed` absences, `countsFrom` date, `excusedMatters`, `late` (`per`, `minutes`), `rule` and `over` in plain words |
| `recurring` | rules like "due Mondays 11:59pm": `title`, `weekday`, `time`, `from`, `until`, `skip` dates |
| `assignments` | `cadence`, `due`, `marking` in words, plus `items` for work the syllabus lists by hand (`n`, `title`, `due`, `submitVia`) |
| `sessions` | dated class sessions (`n`, `date`, `topic`, `path`) for courses taught from a repo or wiki |
| `schedule` | dated milestones (`date`, `what`) for project courses; shows a timeline |
| `clientMeetings`, `team` | for studio or client courses |
| `autoPlan` | kinds of deadline that plan themselves, e.g. `{ "quiz": 2 }` |
| `kit` | Study Kit for this class: `apps` to open, `notes` link (else your profile's), `physical` checklist |
| `gmail.query` | a Gmail search for this class's mail (needs the `gws` CLI) |
| `briefNotes` | how this instructor wants work done; read by the brief writer |
| `note`, `warning` | shown on the class page |
| `recipes` | which recipes setup used for this class (`quiz-course`, `readings-responses`, ...); read by updates, not by the app |

### Source kinds

| kind | what it does | needs |
|---|---|---|
| `brightspace` / `canvas` | a link to the class on the platform (deadlines come from `lmsId`) | the platform connector |
| `site`, `listing` | a class website; read for assignment text if its host is in `publicHosts` | nothing |
| `github` | watches a class repo: new and changed files show up as materials | nothing (a GitHub token raises the rate limit) |
| `github-weekly` | a repo with a README week table (`\| 01 \| 2026-09-04 \|`) and `weeks/NN-...md` files whose `## Homework` section becomes a deadline | nothing |
| `github-wiki-assignments` | a class wiki with one `Assignment-N` page each | `githubWikiName` |
| `github-mine` | your own homework repo; pushes count as progress | nothing |
| `gdoc` | a published Google Doc (syllabus); you get told when it changes | nothing |
| `gsheet-csv` | a published schedule sheet (CSV link) with a `14-Sep` style date column and cells starting Homework / Quiz / Exam / Project; a Recitations column is moved back to its Friday | nothing (other layouts need a plugin) |
| `campuswire` | the class Campuswire feed (`url` has `/c/<group>/`) | `connectors/campuswire/cw login` |
| `discord` | a server link (not read automatically) | nothing |
| `gdrive`, `slides`, `figma`, `recording`, `gdoc-link` | links only, grouped on the class page | nothing |
