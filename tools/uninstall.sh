#!/bin/bash
# Stop Today and remove its background jobs and app copy. Settings (~/.today, ~/.courses.json),
# study history (planner/state.json, ~/.study-ledger.json) and Quiz Prep data stay.
#   tools/uninstall.sh --dry-run | --yes
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${TODAY_PROFILE:-$HOME/.today/profile.json}"
case "${1:-}" in --yes) DRY=0 ;; --dry-run) DRY=1 ;; *) echo "usage: $0 --dry-run | --yes"; exit 2 ;; esac
run() { if [ "$DRY" = 1 ]; then echo "  would: $*"; else eval "$@"; fi; }
LABEL=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('launchLabel') or 'today.planner')" "$PROFILE" 2>/dev/null || echo today.planner)
SYNC_LABEL=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('syncLabel') or '')" "$PROFILE" 2>/dev/null)
for l in "$LABEL" "${SYNC_LABEL:-$LABEL.sync}"; do
  run "launchctl bootout gui/$(id -u) '$HOME/Library/LaunchAgents/$l.plist' 2>/dev/null; true"
  run "rm -f '$HOME/Library/LaunchAgents/$l.plist'"
done
# Quiz Prep runs in a restart loop that Today started: stop the loop, then its server
LOOP=$(pgrep -f "while true; do node server.js" | while read -r pid; do ps -o command= -p "$pid" | grep -q "$ROOT" && echo "$pid"; done)
[ -n "$LOOP" ] && run "kill $LOOP"
NODE=$(lsof -ti tcp:3123 -sTCP:LISTEN 2>/dev/null)
[ -n "$NODE" ] && run "kill $NODE"
run "rm -rf '$ROOT/planner/Today.app'"
echo "done (settings kept)"
