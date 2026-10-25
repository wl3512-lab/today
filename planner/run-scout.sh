#!/bin/bash
# The daily internship run (feature "internships"), fired each morning by the student's LaunchAgent.
#
# Four steps, each allowed to fail on its own:
#   1. company job boards      (intern_scout.py)
#   2. Handshake / LinkedIn    (intern_mail.py)
#   3. the report              (intern_report.py)
#   4. the agent               (claude -p, works the queue and prepares applications)
#
# Steps 1-3 are plain Python and always produce a true report of where things
# stand. Step 4 needs a model and is the only part that can be unavailable, so
# it runs last and its absence costs commentary, not facts.
#
# Where the agent is, the planner's own label and the morning prompt come from
# the profile, through intern_run.py. Nothing here submits an application.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 0
AGENT_REPO="" PLANNER_LABEL=""
eval "$(/usr/bin/python3 intern_run.py env 2>/dev/null)"
AGENT="$AGENT_REPO/scripts"
REPORTS="${INTERNSHIP_AGENT_HOME:-$HOME/.internship-agent}/applications/reports"
TODAY="$(date +%Y-%m-%d)"
LOG="$REPORTS/$TODAY.log"
mkdir -p "$REPORTS"

note() { printf '%s  %s\n' "$(date '+%H:%M:%S')" "$*" >>"$LOG"; }

notify() {  # title, body - a banner is enough here; nothing is time-critical
  /usr/bin/osascript -e "display notification \"${2//\"/}\" with title \"${1//\"/}\"" 2>/dev/null
}

note "=== run start ==="
[ -d "$AGENT" ] || { note "no internship agent at $AGENT - nothing to run"; exit 0; }

# The agent's code lives in its GitHub clone; pull first so today's run is the
# latest version. --ff-only never merges or overwrites local edits: if the
# clone has diverged it just says so and runs what is there.
BEFORE=$(git -C "$AGENT_REPO" rev-parse HEAD 2>/dev/null || echo none)
if git -C "$AGENT_REPO" pull --ff-only --quiet >>"$LOG" 2>&1; then
  AFTER=$(git -C "$AGENT_REPO" rev-parse HEAD)
  if [ "$BEFORE" != "$AFTER" ]; then
    note "agent updated from GitHub: ${BEFORE:0:7} -> ${AFTER:0:7}"
    # the planner's server imported the old code; restart it so the page uses the new
    launchctl kickstart -k "gui/$(id -u)/$PLANNER_LABEL" >>"$LOG" 2>&1 || note "planner restart failed"
  fi
else
  note "agent update skipped (git pull failed - offline, or local changes); running the version on disk"
fi

/usr/bin/python3 "$AGENT/intern_scout.py" >>"$LOG" 2>&1 || note "scout failed"
/usr/bin/python3 "$AGENT/intern_mail.py"  >>"$LOG" 2>&1 || note "mail failed"

# launchd hands a job a PATH without ~/.local/bin, where claude lives. A bare
# `claude` works by hand and fails silently every scheduled run, so resolve it
# absolutely.
CLAUDE=""
for c in "$HOME/.local/bin/claude" /opt/homebrew/bin/claude /usr/local/bin/claude; do
  [ -x "$c" ] && { CLAUDE="$c"; break; }
done
[ -z "$CLAUDE" ] && CLAUDE="$(command -v claude 2>/dev/null || true)"
PROMPT="$(/usr/bin/python3 intern_run.py prompt 2>>"$LOG" || true)"

if [ -n "$CLAUDE" ] && [ -n "$PROMPT" ]; then
  note "agent: working the queue with $CLAUDE"
  # One shot a day means one bad minute costs the day, so try again.
  for i in 1 2 3; do
    "$CLAUDE" -p "$PROMPT" \
      --allowedTools "Read,Write,Edit,Glob,Grep,Bash,Skill,WebFetch" \
      --output-format text >>"$LOG" 2>&1 && { note "agent done"; break; }
    note "agent attempt $i failed"
    [ "$i" -lt 3 ] && sleep $((i * 180))
  done
elif [ -z "$PROMPT" ]; then
  note "no morning prompt (internships.dailyPrompt) - report only, nothing prepared"
else
  note "no claude binary - report only, nothing prepared"
fi

# The report is written last so it reflects anything the agent just prepared.
if /usr/bin/python3 "$AGENT/intern_report.py" >>"$LOG" 2>&1; then
  note "report written"
else
  note "report FAILED"
  notify "Internship scout" "The scan ran but the report failed. See $LOG"
  exit 1
fi

READY=$(/usr/bin/python3 -c "import sys;sys.path.insert(0,'$AGENT');import intern_agent as a,internships;print(a.cmd_status(internships.load())['ready_to_send'])" 2>/dev/null || echo 0)
ASKS=$(/usr/bin/python3 -c "import sys;sys.path.insert(0,'$AGENT');import intern_agent as a,internships;print(a.cmd_status(internships.load())['open_questions'])" 2>/dev/null || echo 0)
notify "Internships — $(date '+%b %-d')" "$READY ready to send, $ASKS waiting on you. Report in the planner."
note "=== run end ==="
