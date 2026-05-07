# GlobalMediaCrawler 🕷️

A robust, multi-platform media crawler that unifies data from YouTube, Reddit, TikTok, Instagram, and X/Twitter into a standardized schema.

## 🚀 Overview

This project provides a unified orchestration layer for crawling social media content. It routes all execution (API, CLI, Workers) through a shared service layer to ensure consistent behavior across different execution models.

**Note:** `docs/superpowers/` contains historical planning artifacts and implementation history for agentic workers. These are not intended as user-facing documentation.

## 📦 Supported Setup Paths

### Mode 1: Simple Mode (Local SQLite + File Export)
Ideal for personal use and quick scrapes without complex infrastructure.

1. **Setup Environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements-base.txt
   ```

2. **Configure:**
   ```bash
   cp .env.example .env
   # Set SIMPLE_MODE=true in .env
   ```

3. **Run via CLI:**
   ```bash
   python run.py search --platform youtube --keyword "AI news" --limit 5
   ```

4. **Run via API:**
   ```bash
   uvicorn app.main:app --reload
   # Health check: curl http://localhost:8000/api/health
   ```

### Mode 2: Full Mode (PostgreSQL + Redis + Celery)
Ideal for production-scale distributed crawling.

1. **Start Infrastructure:**
   ```bash
   docker-compose up -d
   ```

2. **Setup Environment & DB:**
   ```bash
   pip install -r requirements-base.txt
   cp .env.example .env
   # Ensure DATABASE_URL and REDIS_URL are correct in .env
   alembic upgrade head
   ```

3. **Run API & Worker:**
   ```bash
   # Terminal 1: API
   uvicorn app.main:app --reload

   # Terminal 2: Celery Worker
   celery -A app.core.task_queue:celery_app worker --loglevel=info
   ```

## 🛠 Features & Architecture

- **Unified Service Layer**: `app/services/crawl_service.py` owns the crawl flow.
- **Pluggable Crawlers**: `app/crawlers/` supports YouTube (API/Playwright/yt-dlp), Reddit, TikTok, Instagram, and X.
- **Standardized Storage**: `app/storage/` supports JSONL, CSV, and PostgreSQL.
- **Media Download**: `app/services/media_service.py` handles media extraction.

## 🧪 Quality Gates

We enforce high code quality via automated tools:
```bash
# Run all tests
venv/bin/python -m pytest

# Lint and Format check
venv/bin/python -m ruff check app tests
venv/bin/python -m ruff format --check app tests

# Type check
venv/bin/python -m pyright app tests
```

---
Developed by sqoder.
