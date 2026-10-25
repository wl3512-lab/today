# Recipe: internship search (optional)

**Fits:** a student looking for internships who wants postings ranked and applications prepared (never submitted) beside their planner.

## Set up
1. Clone the agent beside the planner: `git clone https://github.com/wl3512-lab/internship-agent internship-agent` in the repo root (the folder name matters: the planner page loads `../internship-agent/ui`). If they already have a clone, link it there instead.
2. Run its own setup: in Claude Code, `/plugin marketplace add wl3512-lab/internship-agent`, `/plugin install internship-agent@internship-agent`, then `/internship-setup`. It interviews them once (résumé, school, graduation year, where they can and want to work) and writes its profile.
3. Turn the feature on: add `"internships"` to profile `features`.
4. Optional daily scout: a LaunchAgent with its own label (profile `internships.scoutLabel`) running `planner/run-scout.sh` in the morning. Ask before installing anything that runs on a schedule.

## Check
- The planner sidebar shows Internships, and the page lists postings after the first scout run.
