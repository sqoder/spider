#!/usr/bin/env bash
set -euo pipefail

# ============================================
# GlobalMediaCrawler - First-time Setup
# ============================================
# Usage: bash bin/setup.sh [--with-postgres]
#   --with-postgres  Use PostgreSQL instead of SQLite

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "=== GlobalMediaCrawler Setup ==="
echo ""

# ---- Detect Python ----
PYTHON=""
for cmd in python3.14 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Install Python 3.10+ first."
    exit 1
fi

PY_VERSION=$("$PYTHON" --version 2>&1)
echo "Using: $PY_VERSION"

# ---- Virtual Env ----
if [ ! -d "venv" ]; then
    echo ""
    echo ">>> Creating virtual environment..."
    "$PYTHON" -m venv venv
else
    echo ""
    echo ">>> Virtual environment already exists"
fi

source venv/bin/activate

# ---- Install Dependencies ----
echo ""
echo ">>> Installing dependencies..."

if [ -f "requirements-extra.txt" ]; then
    pip install -r requirements-extra.txt
fi
pip install -r requirements-base.txt

# ---- Playwright for YouTube scraper ----
if command -v playwright &>/dev/null; then
    echo ""
    echo ">>> Installing Playwright browsers..."
    playwright install chromium 2>/dev/null || echo "    (skipped, install manually: playwright install)"
fi

# ---- Data Directory ----
mkdir -p data media

# ---- Database Setup ----
if [ "${1:-}" = "--with-postgres" ]; then
    echo ""
    echo "=== PostgreSQL Setup ==="

    if ! command -v psql &>/dev/null; then
        echo "WARNING: PostgreSQL not found. Install with: brew install postgresql@16"
        echo "Falling back to SQLite..."
        echo ""
        # Copy SQLite config
        if [ ! -f ".env" ]; then
            cp .env.sqlite .env
            echo "Created .env from .env.sqlite"
        fi
    else
        echo "PostgreSQL found: $(psql --version)"

        # Create DB user if not exists
        psql -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='crawler'" 2>/dev/null | grep -q 1 \
            && echo "User 'crawler' already exists" \
            || psql -U postgres -c "CREATE USER crawler WITH PASSWORD 'crawler_pass';"

        # Create database if not exists
        psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='global_media_crawler'" 2>/dev/null | grep -q 1 \
            && echo "Database 'global_media_crawler' already exists" \
            || psql -U postgres -c "CREATE DATABASE global_media_crawler OWNER crawler;"

        echo ""
        echo ">>> Running Alembic migrations..."
        alembic upgrade head
    fi
else
    echo ""
    echo ">>> Using SQLite (default)"

    # Copy SQLite config if no .env exists
    if [ ! -f ".env" ]; then
        cp .env.sqlite .env
        echo "Created .env from .env.sqlite"
    else
        echo "Using existing .env"
    fi

    # Ensure data dir exists for SQLite
    mkdir -p data

    # Auto-create tables via app startup (AUTO_CREATE_TABLES=true)
    # or run migrations manually:
    echo "    Tables auto-created on first app start (AUTO_CREATE_TABLES=true)"
    echo "    Or run: alembic upgrade head (requires DATABASE_URL in alembic.ini)"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next step:"
echo "  bash bin/dev.sh"
echo ""
echo "Optional: configure API keys in .env"
echo "  YOUTUBE_API_KEY=...    (leave empty for yt-dlp fallback)"
echo "  REDDIT_CLIENT_ID=..."
echo "  REDDIT_CLIENT_SECRET=..."
