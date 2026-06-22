#!/usr/bin/env bash
# Lingua Nova — run the PhD Master Dashboard
set -e

# Load .env if it exists
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Make sure data dir exists
mkdir -p data

PYTHON_BIN="${PYTHON_BIN:-python}"
STREAMLIT_BIN="${STREAMLIT_BIN:-streamlit}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [ -x ".venv/bin/streamlit" ]; then
  STREAMLIT_BIN=".venv/bin/streamlit"
fi

# Initialize DB if missing
"$PYTHON_BIN" -c "from core.db import init_db; init_db()" 2>/dev/null || true

"$STREAMLIT_BIN" run app.py --server.address=0.0.0.0 --server.port=8501 --browser.gatherUsageStats=false
