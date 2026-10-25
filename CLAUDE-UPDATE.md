# Updating an install (instructions for Claude)

Use this when someone with Today installed asks to update it.

1. Check for local changes first: `git status`. If they (or you, earlier) edited
   files in the checkout, list them and ask whether to keep them. Stash before
   pulling if they want to keep them, then reapply.
2. Show what changed: `git fetch`, then read `CHANGELOG.md` on `origin/main`
   for every version newer than the local `VERSION`. Tell them in a few lines.
3. If an entry says settings change, show them the exact edit to
   `~/.today/profile.json` or `~/.courses.json` and ask before making it.
   Never rewrite those files wholesale.
4. `git pull --ff-only`.
5. Run the tests: `planner/.venv/bin/python planner/tests/run.py`, and
   `for t in quiz-prep/tests/*.test.js; do node "$t"; done`.
   Stop and report if any fail; don't restart a broken version.
6. `python3 tools/doctor.py`.
7. Restart: `launchctl kickstart -k gui/$(id -u)/<launchLabel>` (the label in
   their profile, default `today.planner`). Quiz Prep restarts on its own when
   its files change.
8. If something breaks after the update, `git checkout <previous tag>` and
   restart. Their settings and study history are untouched by updates.
