#!/bin/bash
# Double-click this file to start Quiz Prep.
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not installed. Get the LTS version from https://nodejs.org, then double-click this file again."
  open "https://nodejs.org"
  read -n 1 -p "Press any key to close."
  exit 1
fi
echo "Node $(node -v) found."
echo "Checking tools..."
npm install --silent --no-audit --no-fund
# Stop an older copy of Quiz Prep if one is still running on its port.
pkill -f "while true; do node server.js" 2>/dev/null
OLD=$(lsof -ti tcp:3123 -sTCP:LISTEN 2>/dev/null); [ -n "$OLD" ] && kill $OLD && sleep 1
(sleep 2 && open "http://localhost:3123") &
npm start
