# Setting up Today for someone (instructions for Claude)

You are installing Today, a Mac menu bar planner for students, plus Quiz Prep,
for the person you are talking to. Today only works if it knows their classes,
so most of setup is a short interview. You then write two settings files,
install the app and check that it works.

Read this whole file before the first question. Read the recipes in
`recipes/` and the field reference in `templates/SETTINGS.md` before you
write any settings.

## How to run the interview

- Ask in small rounds of one to four questions. Use the AskUserQuestion tool
  when you have it, with choices for anything that has common answers.
- Ask for documents before typing. A syllabus PDF, a screenshot of their
  registration page or a link to a class site answers ten questions at once.
  Read what they give you and ask only about what it leaves out.
- Offer the default and move on. Study hours of 10:00 to 22:00, one-hour
  sessions and the generic recipe are fine for most people.
- Say why you are asking when it isn't obvious ("so study sessions never land
  on your class time").
- Many students find starting the hardest part. Keep the setup itself easy to
  start: tell them up front it takes about 15 minutes and what you need from
  them (syllabi, their school sign-in).
- Settings stay on their Mac. Never commit `~/.today/` or `~/.courses.json`,
  and treat the calendar's secret iCal address like a password.

## Round 0: can this Mac run it?

Check quietly, then report only problems:

- macOS (Today has no Windows or Linux version yet).
- A framework Python 3.9+ (`tools/install.sh` looks for python.org or
  Homebrew Python). If missing, have them install it from python.org.
- Node.js 18+ for Quiz Prep (optional: without it Quiz Prep stays off).
- The `claude` command, which writes assignment briefs and answers Quiz Prep
  questions. They are talking to you, so it is usually there.

Tell them what will happen: a folder (this checkout), two settings files, a
menu bar app and a background job that refreshes their classes every two
hours. Get a yes before installing anything.

## Round 1: about them

1. What should Today call you? (first name)
2. School name.
3. Time zone. Read it from the Mac (`readlink /etc/localtime`) and confirm.
4. Year or program, in a few words ("second-year design student"). The AI
   helpers use it to pitch explanations.

## Round 2: where their classes live

1. Which learning platform does the school use? Brightspace (D2L), Canvas,
   Moodle, Blackboard, or none.
2. Ask them to paste the link of any class page on it. Take the address part
   for `lms.host` (for example `canvas.stateu.edu`) and the number in the URL
   as that class's `lmsId`.
3. Where else does homework show up? (pick all) Class websites, GitHub,
   Gradescope, Campuswire, a published Google Sheet schedule, email, paper
   handouts.

Platform support:

| platform | what to do |
|---|---|
| Brightspace | ready: `connectors/brightspace/bs`. Needs agent-browser (`npm install -g agent-browser && agent-browser install`). They sign in once in a window. |
| Canvas | ready: `connectors/canvas/canvas`. They make a personal access token in Canvas (Account, Settings, New Access Token) and paste it into `canvas login`. |
| Moodle, Blackboard, Schoology | not built yet. Offer to write a connector following `connectors/CONNECTOR.md` (Moodle has a student token API), test it on their account, and keep it in their checkout. Or skip the platform and enter deadlines from the syllabus. |
| none | skip. Deadlines come from syllabi, class sites and GitHub. |

## Round 3: their classes (the main part)

1. "Drop in your class schedule (a screenshot of your registration page works)
   and every syllabus you have." Read them.
2. For each class, fill in everything the generic recipe asks for that the
   documents answer: name, code, meeting times and room, instructor, TA,
   office hours, grading weights, attendance rule, recurring due dates.
3. Ask one question per class about what it needs (multi-select):
   - Quizzes or exams I need to study for: `recipes/quiz-course.md` (turns on Quiz Prep)
   - Readings and weekly responses or posts: `recipes/readings-responses.md`
   - Coding, with the class on GitHub: `recipes/coding-github.md`
   - A team, client or studio project: `recipes/studio-meetings.md`
   - Only deadlines and grades: `recipes/generic.md`
4. Follow each chosen recipe and ask only the questions it lists that the
   syllabus left open. Record the choices in the course as
   `"recipes": ["quiz-course"]` so updates know what each class uses.
5. For the Study Kit, ask per class which apps they open to work on it and
   what they need on the desk. Offer to skip; there are defaults.

Show a short table of the classes (name, meeting time, platform id, recipes)
and ask them to confirm before you write anything.

## Round 4: how they study

1. When can study sessions go? Default 10:00 to 22:00. Ask about standing
   commitments (work shifts, practice, gym) only if they want those kept free;
   those go on their calendar, which Today reads in the next round.
2. How long should one sitting be? Default 60 minutes.
3. A notes page to open when they start (Notion, Google Docs, Apple Notes
   link). Optional.
4. A study playlist link (SoundCloud, YouTube, Spotify web). Optional.
5. Focus mode: Today can switch on a "Study" Focus when they start. They make
   two Shortcuts named **Study** (Set Focus, Do Not Disturb, On) and
   **Study Off**. Optional; offer to walk them through it.

## Round 5: calendar and mail (optional)

1. Google Calendar: the secret address in iCal format (Calendar settings, the
   calendar, Integrate calendar) goes in `calendar.ics`, so planned study
   sessions avoid their events. iCloud and Outlook calendars publish an ICS
   link too.
2. Gmail per class (`gmail.query`) needs the Google Workspace CLI `gws`
   signed in to their mail. Offer it only if a class communicates mostly by
   email.

## Round 6: extras

- Internship search: `recipes/internships.md`. Ask only if they mention
  internships or jobs.

## Write the settings

1. `~/.today/profile.json` from `templates/profile.example.json`. Keep
   `launchLabel` as `today.planner` unless that label is taken on this Mac.
2. `~/.courses.json` from `templates/courses.example.json`. If the file
   exists already, show them what is in it and ask before replacing it.
3. Quiz courses: add each key to `quizPrep.courses` and fill
   `quizPrep.settings.<key>`.
4. Run `python3 tools/doctor.py` and fix every line starting with `!!`.

## Sign in to the platform

- Brightspace: `python3 connectors/brightspace/bs login`. A window opens; they
  sign in with their school account (and Duo, if the school uses it) and tick
  "remember this device" if offered.
- Canvas: `python3 connectors/canvas/canvas login` and paste the token.
- Campuswire: `python3 connectors/campuswire/cw --group <id> login`.
- Then `python3 tools/doctor.py --live` to confirm the sign-in works.

## Install

1. `tools/install.sh --dry-run`, then tell them in one or two lines what it
   will do.
2. On their yes, `tools/install.sh --yes`. It builds `planner/Today.app`,
   runs the first class sync and starts the menu bar app.
3. The blue heart appears in the menu bar. If not, check
   `/tmp/today.planner.err`, then menu bar managers such as Ice or Bartender
   hiding new icons.

## First look (do this together)

1. Open Planner from the menu bar heart. Check that Today shows their next
   class and the nearest deadlines. Missing a class or deadline: fix the
   course entry and run `python3 planner/study_sync.py`.
2. Platform classes they skipped show up with "Not in your course registry".
   Add each one, or put it in `ignore`.
3. Tap a homework card: its page shows a brief (what it is, steps with
   minutes) and **Plan it** places sessions around their classes.
4. Press start on one assignment to try the Study Kit: links and apps open,
   the Focus turns on and the 25/5 timer begins.
5. For a quiz class, open the Study Kit and build a kit for the next quiz
   with one real slide file in Downloads.

## When something fails

- `python3 tools/doctor.py` names most problems.
- Logs: `/tmp/<launchLabel>.err` (menu bar app), `/tmp/<launchLabel>.sync.err`
  (sync), `~/.quiz-prep.log`.
- A platform session that expired shows as "session expired, run: ... login".
- Undo everything with `tools/uninstall.sh --yes`. Settings stay.

## Afterwards

- Classes change: edit `~/.courses.json` (or ask Claude to) and run the sync.
  Put dropped classes in `ignore` with their `lmsId`.
- New term: run Round 3 again for the new classes and move the old ones to
  `ignore`.
- Updates: `CLAUDE-UPDATE.md`.
