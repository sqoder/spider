#!/usr/bin/env bash
set -euo pipefail

# ============================================
# Start just the FastAPI server
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "ERROR: No virtualenv. Run 'bash bin/setup.sh' first."
    exit 1
fi
source venv/bin/activate

mkdir -p data media

echo ">>> API at http://localhost:8000  |  docs at http://localhost:8000/docs"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
