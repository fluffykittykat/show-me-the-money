#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source .env file if present (loads API keys etc)
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

# Defaults for anything not in .env
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://jerry:maguire@localhost:5432/followthemoney}"
export AUTO_SEED="${AUTO_SEED:-false}"

source "${SCRIPT_DIR}/venv/bin/activate" 2>/dev/null || true
cd "${SCRIPT_DIR}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
