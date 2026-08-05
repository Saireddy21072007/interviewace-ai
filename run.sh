#!/usr/bin/env bash
# ===========================================================================
#  InterviewAce AI - one-command launcher (macOS / Linux)
#
#    ./run.sh          install anything missing, then start API + web app
#    ./run.sh setup    install dependencies only
#    ./run.sh test     run the Python test suite
#    ./run.sh api      start only the backend  (http://localhost:8000/docs)
#    ./run.sh web      start only the frontend (http://localhost:5173)
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

ACTION="${1:-start}"
PY="$(command -v python3 || command -v python)"

if [ -z "$PY" ]; then
  echo "[X] Python 3.11+ is required but was not found."
  exit 1
fi

if [ "$ACTION" = "test" ]; then
  exec "$PY" -m pytest tests -q
fi

[ -f .env ] || { echo "[~] Creating .env from .env.example"; cp .env.example .env; }

if [ ! -f .deps-installed ]; then
  echo "[~] Installing Python packages (first run only)..."
  "$PY" -m pip install --disable-pip-version-check -q -r backend/requirements.txt
  touch .deps-installed
fi

start_api() {
  "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
}

if [ "$ACTION" = "api" ]; then
  echo "[~] API on http://localhost:8000 (docs at /docs)"
  start_api
  exit 0
fi

if ! command -v npm >/dev/null; then
  echo "[!] npm not found - install Node.js 18+ from https://nodejs.org"
  [ "$ACTION" = "web" ] && exit 1
  echo "    Starting the API only."
  start_api
  exit 0
fi

[ -d frontend/node_modules ] || {
  echo "[~] Installing web packages (first run only)..."
  (cd frontend && npm install --no-fund --no-audit)
}

if [ "$ACTION" = "web" ]; then
  cd frontend && exec npm run dev
fi

if [ "$ACTION" = "setup" ]; then
  echo "[OK] Setup complete. Run ./run.sh to start the app."
  exit 0
fi

echo
echo "  InterviewAce AI"
echo "  ---------------"
echo "  API      http://localhost:8000/docs"
echo "  Web app  http://localhost:5173"
echo

start_api &
API_PID=$!
# Stop the backend whenever this script exits, so Ctrl-C does not leave an
# orphaned uvicorn holding port 8000.
trap 'kill $API_PID 2>/dev/null || true' EXIT INT TERM

cd frontend && npm run dev
