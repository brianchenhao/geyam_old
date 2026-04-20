#!/usr/bin/env bash
# GEYAM local startup — run this from the geyam/ directory
# Opens Postgres in Docker, activates venv, starts uvicorn, waits for /health
set -e

cd "$(dirname "$0")"

echo "==> 1/4  Starting Postgres..."
docker-compose up -d db

echo "==> 2/4  Waiting for Postgres to accept connections..."
until docker-compose exec -T db pg_isready -U pos_user -d geyam >/dev/null 2>&1; do
  sleep 1
done
echo "    Postgres is up."

echo "==> 3/4  Installing Python deps (if venv missing)..."
cd backend

# Cross-platform: Windows venvs use Scripts/, Unix uses bin/
if [ -d ".venv/Scripts" ]; then
  VENV_BIN=".venv/Scripts"
elif [ -d ".venv/bin" ]; then
  VENV_BIN=".venv/bin"
else
  # Actually test each candidate — on Windows, `python3` may be the MS Store stub.
  # Prefer 3.12: numpy<2 / ultralytics ship no wheels for 3.13+, and source
  # builds need a C toolchain that Device Guard may block on Windows.
  PY=""
  if py -3.12 --version >/dev/null 2>&1; then
    PY="py -3.12"
  else
    for candidate in python3.12 python python3 py; do
      if $candidate --version 2>&1 | grep -q "Python 3.1[012]"; then PY="$candidate"; break; fi
    done
  fi
  if [ -z "$PY" ]; then
    echo "ERROR: no Python 3.10–3.12 found (required for numpy<2 / ultralytics)" >&2
    exit 1
  fi
  $PY -m venv .venv
  if [ -d ".venv/Scripts" ]; then VENV_BIN=".venv/Scripts"; else VENV_BIN=".venv/bin"; fi
  # Use `python -m pip` — on Windows, pip.exe can't self-upgrade while running.
  if [ -x "$VENV_BIN/python.exe" ]; then VENV_PY="$VENV_BIN/python.exe"; else VENV_PY="$VENV_BIN/python"; fi
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r requirements.txt
fi



echo "==> 4/4  Starting FastAPI on http://localhost:8509 ..."
echo "    (Ctrl+C to stop. Open another terminal and run: curl http://localhost:8509/health )"
# Put the venv first on PATH so uvicorn's --reload subprocess uses THIS venv
# (not a neighbor project's .venv that happens to also have uvicorn installed).
export PATH="$(pwd)/$VENV_BIN:$PATH"
if [ -x "$VENV_BIN/python.exe" ]; then VENV_PY="$VENV_BIN/python.exe"; else VENV_PY="$VENV_BIN/python"; fi
exec "$VENV_PY" -m uvicorn main:app --reload --host 0.0.0.0 --port 8509

