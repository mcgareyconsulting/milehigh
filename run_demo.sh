#!/usr/bin/env bash
# One-command launcher for the meeting -> checklist demo.
# Pins the 3 footguns: runs from the worktree (correct `app/`), forces ENVIRONMENT=local,
# and uses an ABSOLUTE sqlite path so the seeded DB (boneill + 40 items) is always used
# regardless of where you launch from.
set -uo pipefail

WT="/Users/danielmcgarey/Desktop/MHMW/worktree/feature/meeting-checklist-todo"
PY="/Users/danielmcgarey/Desktop/MHMW/milehigh/.venv/bin/python"

export ENVIRONMENT=local
export CHECKLIST_EXTRACT_MODEL=claude-opus-4-8
export LOCAL_DATABASE_URL="sqlite:///$WT/instance/jobs.sqlite"

cd "$WT"

echo "Backend  : http://localhost:8000   (DB: $WT/instance/jobs.sqlite)"
"$PY" run.py > /tmp/flask_demo.log 2>&1 &
BACK=$!

echo "Frontend : http://localhost:5173"
( cd frontend && npm run dev -- --port 5173 > /tmp/vite_demo.log 2>&1 ) &
FRONT=$!

cleanup() {
  echo; echo "stopping..."
  kill "$BACK" "$FRONT" 2>/dev/null
  pkill -f "vite --port 5173" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

sleep 4
echo
echo "  ▶ Open:  http://localhost:5173/meetings"
echo "  ▶ Login: boneill@mhmw.com / demo"
echo "  ▶ Logs:  /tmp/flask_demo.log  |  /tmp/vite_demo.log"
echo "  ▶ Ctrl-C to stop both servers."
echo
wait
