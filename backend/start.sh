#!/bin/bash
# Load .env if present, otherwise use defaults
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://jerry:maguire@localhost:5432/followthemoney}"
export AUTO_SEED="${AUTO_SEED:-false}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/venv/bin/activate" 2>/dev/null || true
cd "${SCRIPT_DIR}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
