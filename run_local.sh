#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x venv/bin/python ]; then
  PYTHON=venv/bin/python
elif [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
else
  echo 'Create a virtual environment and install requirements.txt first.' >&2
  exit 1
fi
# Use a separate preview database; never reset the original event records.
export DATABASE_PATH="${DATABASE_PATH:-$PWD/database/local_preview.db}"
export PORT="${PORT:-5050}"
exec "$PYTHON" app.py
