#!/bin/bash
# Launch the Today menubar planner.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First run — setting up a little Python venv…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet rumps
fi

exec ./.venv/bin/python app.py
