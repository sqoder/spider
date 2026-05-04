#!/usr/bin/env bash
set -euo pipefail

# ============================================
# GlobalMediaCrawler - Dev Server (no Docker)
# ============================================
# Usage:
#   bash bin/dev.sh              # API only (simple mode, SQLite)
#   bash bin/dev.sh --full       # API + Celery worker + Beat
#   bash bin/dev.sh --postgres   # API with PostgreSQL

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-simple}"
SIMPLE=true
USE_POSTGRES=false

if [ "$MODE" = "--full" ]; then
    SIMPLE=false
    echo "=== Starting in FULL mode (API + Celery Worker) ==="
elif [ "$MODE" = "--postgres" ]; then
    USE_POSTGRES=true
    echo "=== Starting in PostgreSQL mode ==="
else
    echo "=== Starting in SIMPLE mode (no Celery/Redis) ==="
fi

# ---- Source virtual env ----
if [ ! -d "venv" ]; then
    echo "ERROR: No virtualenv found. Run 'bash bin/setup.sh' first."
    exit 1
fi
source venv/bin/activate

# ---- Env file ----
if [ "$USE_POSTGRES" = true ] && [ ! -f ".env" ]; then
    echo "ERROR: No .env found. Create one from .env.example"
    exit 1
fi

echo "Using: $(python --version)"
echo ""

# ---- Infrastructure (optional) ----
if [ "$USE_POSTGRES" = true ]; then
    echo "Starting PostgreSQL (via brew services)..."
    brew services start postgresql@16 2>/dev/null || echo "  (already running or unavailable)"
fi

if [ "$SIMPLE" = false ]; then
    echo "Starting Redis (via brew services)..."
    brew services start redis 2>/dev/null || echo "  (already running or unavailable)"
fi

# ---- Ensure data dirs ----
mkdir -p data media

# ---- Start ----
echo ""
echo ">>> Starting FastAPI server on http://localhost:8000"
echo "    API docs: http://localhost:8000/docs"
echo ""

if [ "$SIMPLE" = true ]; then
    # Simple mode: just the API server
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
else
    # Full mode: API + Worker in background
    echo "Starting Celery worker..."
    celery -A app.core.task_queue:celery_app worker --loglevel=info -Q crawl,media &
    CELERY_PID=$!

    echo "Starting FastAPI..."
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    # Cleanup worker on exit
    kill $CELERY_PID 2>/dev/null || true
fi
