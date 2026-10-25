# Today

A Mac menu bar planner for students (`planner/`), Quiz Prep for quiz classes
(`quiz-prep/`), and connectors for school platforms (`connectors/`).

- Someone wants it set up: follow `CLAUDE-SETUP.md` step by step.
- Someone wants to update: follow `CLAUDE-UPDATE.md`.
- Settings live outside the repo (`~/.today/profile.json`, `~/.courses.json`),
  described in `templates/SETTINGS.md`. Keep code free of anything about one
  person or school; put it in their settings or in a plugin under
  `~/.today/plugins/`.

## Working on the code

- Python 3.9+, standard library plus `rumps` and PyObjC for the menu bar app.
  Plain JavaScript in `planner/planner.html`. Node 18+ and Express for Quiz Prep.
- Tests: `planner/.venv/bin/python planner/tests/run.py` (after install; runs as a made-up student, includes
  `connectors/tests`), `node planner/tests/<name>.test.js`, and
  `node quiz-prep/tests/<name>.test.js`.
- Before a commit: the tests pass and `python3 tools/privacy_scan.py` reports
  0 hits.
- AI rule for Quiz Prep: the AI copies numbers and writes words; code computes
  every answer (`quiz-prep/lib/calc.js`).
- Publishing (maintainer only): bump `VERSION`, add a `CHANGELOG.md` entry,
  commit, then `tools/publish.sh --yes`. Never `git push` a branch directly;
  the pre-push hook (`git config core.hooksPath tools/hooks`) refuses it.
