#!/bin/bash
# Install Today on this Mac for the person whose settings are in ~/.today/profile.json.
#   tools/install.sh --dry-run    print every step, change nothing
#   tools/install.sh --yes        do it
#   tools/install.sh --yes --no-jobs   build everything but install no background jobs (for testing)
# Run the setup interview first (CLAUDE-SETUP.md): it writes the profile and ~/.courses.json.
# Undo with tools/uninstall.sh. Settings and study history are never touched by either.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLANNER="$ROOT/planner"
AGENTS="$HOME/Library/LaunchAgents"
UIDN=$(id -u)
PROFILE="${TODAY_PROFILE:-$HOME/.today/profile.json}"
case "${1:-}" in --yes) DRY=0 ;; --dry-run) DRY=1 ;; *) echo "usage: $0 --dry-run | --yes"; exit 2 ;; esac
run() { if [ "$DRY" = 1 ]; then echo "  would: $*"; else eval "$@" || fail "step failed: $*"; fi; }
fail() { echo "STOP: $*"; exit 1; }
note() { echo "  note: $*"; }

echo "1/6 this Mac has what Today needs"
[ "$(uname)" = Darwin ] || fail "Today runs on macOS only"
# A framework build of Python (python.org or Homebrew): its Python.app is what gives the menu bar icon an identity.
PY=""
for cand in /Library/Frameworks/Python.framework/Versions/3.1[0-9]/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
  [ -x "$cand" ] || continue
  if "$cand" -c 'import sys,os; sys.exit(0 if sys.version_info >= (3,9) and os.path.isdir(os.path.join(sys.base_prefix,"Resources","Python.app")) else 1)' 2>/dev/null; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "no framework Python 3.9+ found. Install Python from https://www.python.org/downloads/macos/ and run this again."
PYAPP="$("$PY" -c 'import sys,os; print(os.path.join(sys.base_prefix,"Resources","Python.app"))')"
echo "  python: $PY"
[ -f "$PROFILE" ] || fail "no profile at $PROFILE. Do the setup interview first (CLAUDE-SETUP.md)."
"$PY" -c "import json,sys; json.load(open(sys.argv[1]))" "$PROFILE" 2>/dev/null || fail "$PROFILE is not valid JSON"
LABEL=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1])).get('launchLabel') or 'today.planner')" "$PROFILE")
SYNC_LABEL=$("$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('syncLabel') or (d.get('launchLabel') or 'today.planner') + '.sync')" "$PROFILE")
COURSES=$("$PY" -c "import json,os,sys; print(os.path.expanduser(json.load(open(sys.argv[1])).get('coursesPath') or '~/.courses.json'))" "$PROFILE")
[ -f "$COURSES" ] || fail "no course list at $COURSES. Do the setup interview first."
"$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); assert isinstance(d.get('courses'), list)" "$COURSES" 2>/dev/null \
  || fail "$COURSES needs a \"courses\" list (see templates/courses.example.json)"
if command -v node >/dev/null 2>&1; then echo "  node: $(node --version)"; else note "no Node.js: Quiz Prep stays off until you install it (https://nodejs.org)"; fi
command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ] || note "no claude command: assignment briefs and the AI helpers need Claude Code"

for l in "$LABEL" "$SYNC_LABEL"; do
  existing="$AGENTS/$l.plist"
  if [ -f "$existing" ] && ! grep -q "<string>$PLANNER</string>" "$existing"; then
    fail "$l is already installed from another folder ($existing). Run that copy's tools/uninstall.sh, or set a different launchLabel/syncLabel in the profile."
  fi
done
NO_JOBS=0; [ "${2:-}" = "--no-jobs" ] && NO_JOBS=1

echo "2/6 a private Python environment with the menu bar libraries"
VENV="$PLANNER/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  run "'$PY' -m venv '$VENV'"
fi
run "'$VENV/bin/pip' install --quiet --upgrade pip"
run "'$VENV/bin/pip' install --quiet rumps pyobjc-framework-WebKit"
SITE=$([ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])' || echo "$VENV/lib/site-packages")

echo "3/6 Today.app: its own copy of Python.app, so macOS shows the menu bar icon"
# Under the shared Python identity macOS parks a menu bar item off screen with no error.
APP="$PLANNER/Today.app"
run "rm -rf '$APP'"
# python.org's _CodeSignature is readable only by root; codesign below writes a new one anyway
run "rsync -a --exclude _CodeSignature '$PYAPP/' '$APP/'"
run "/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier $LABEL.runner' '$APP/Contents/Info.plist'"
run "/usr/libexec/PlistBuddy -c 'Set :CFBundleName Today' '$APP/Contents/Info.plist'"
run "/usr/libexec/PlistBuddy -c 'Add :CFBundleDisplayName string Today' '$APP/Contents/Info.plist' 2>/dev/null || /usr/libexec/PlistBuddy -c 'Set :CFBundleDisplayName Today' '$APP/Contents/Info.plist'"
run "/usr/libexec/PlistBuddy -c 'Add :LSUIElement bool true' '$APP/Contents/Info.plist' 2>/dev/null || /usr/libexec/PlistBuddy -c 'Set :LSUIElement true' '$APP/Contents/Info.plist'"
run "codesign --force --deep --sign - '$APP' 2>/dev/null"
run "PYTHONPATH='$SITE' '$APP/Contents/MacOS/Python' -c 'import rumps'"

echo "4/6 first course sync (this can take a few minutes the first time)"
run "cd '$PLANNER' && PATH=\"\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH\" '$PY' study_sync.py || true"

echo "5/6 background jobs: $LABEL (menu bar) and $SYNC_LABEL (classes every 2 hours)"
ENVPATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
write_agent() {  # label, keepalive|interval, program args...
  local label="$1" mode="$2"; shift 2
  local plist="$AGENTS/$label.plist" args=""
  for a in "$@"; do args="$args<string>$a</string>"; done
  local sched='<key>KeepAlive</key><true/>'
  [ "$mode" = interval ] && sched='<key>StartInterval</key><integer>7200</integer>'
  run "mkdir -p '$AGENTS'"
  run "cat > '$plist' <<PLIST
<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
<key>Label</key><string>$label</string>
<key>ProgramArguments</key><array>$args</array>
<key>WorkingDirectory</key><string>$PLANNER</string>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>$ENVPATH</string><key>PYTHONPATH</key><string>$SITE</string></dict>
<key>RunAtLoad</key><true/>
$sched
<key>StandardOutPath</key><string>/tmp/$label.log</string>
<key>StandardErrorPath</key><string>/tmp/$label.err</string>
</dict></plist>
PLIST"
  run "launchctl bootout gui/$UIDN '$plist' 2>/dev/null; true"
  run "launchctl bootstrap gui/$UIDN '$plist'"
}
if [ "$NO_JOBS" = 1 ]; then echo "  skipped (--no-jobs)"; else
write_agent "$LABEL" keepalive "$APP/Contents/MacOS/Python" "$PLANNER/app.py"
write_agent "$SYNC_LABEL" interval "$PY" "$PLANNER/study_sync.py"
fi

echo "6/6 check"
if [ "$DRY" = 0 ] && [ "$NO_JOBS" = 0 ]; then
  sleep 3
  launchctl print "gui/$UIDN/$LABEL" 2>/dev/null | grep -q "state = running" && echo "  Today is running: look for the blue heart in the menu bar" \
    || note "Today did not start; see /tmp/$LABEL.err"
  "$PY" "$ROOT/tools/doctor.py" || true
elif [ "$DRY" = 1 ]; then
  echo "  dry run: nothing changed"
else
  "$PY" "$ROOT/tools/doctor.py" || true
fi
