# GlobalMediaCrawler 🕷️

A robust, multi-platform media crawler that unifies data from YouTube, Reddit, TikTok, Instagram, and X/Twitter into a standardized schema. Built with FastAPI, Celery, Redis, PostgreSQL, and SQLAlchemy.

## 🚀 Features

- **Unified Data Schema**: All platforms normalize content into `Task`, `Post`, and `Author` models.
- **Asynchronous Processing**: Uses Celery and Redis to handle tasks in the background with auto-retry mechanisms.
- **Rate Limit & Proxy**: Advanced request routing and rate limit protections per platform.
- **Supported Platforms & Strategies**:
  - **YouTube**: Official API + Playwright fallback.
  - **Reddit**: OAuth2 scraping agent.
  - **TikTok**: Subprocess integration with `gallery-dl` and `yt-dlp` (supports single video bypass).
  - **Instagram**: Deep extraction via `gallery-dl` (Cookie auth required for stability).
  - **X / Twitter**: Web scraping without API keys via `twscrape`.

## 📦 Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sqoder/GlobalMediaCrawler.git
   cd GlobalMediaCrawler
   ```

2. **Setup virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Install external dependencies (for TikTok / X):**
   ```bash
   # Make sure you have gallery-dl, yt-dlp, and twscrape
   pip install gallery-dl yt-dlp twscrape playwright
   playwright install
   ```

4. **Environment Variables:**
   Copy `.env.example` to `.env` and fill in the necessary keys.
   ```bash
   cp .env.example .env
   ```

5. **Start Infrastructure (Redis & PostgreSQL):**
   ```bash
   docker-compose up -d
   ```

6. **Initialize Database:**
   ```bash
   alembic upgrade head
   ```

7. **Run the API & Worker:**
   ```bash
   # Start the API server
   uvicorn app.main:app --reload

   # Start the Celery Worker
   celery -A app.core.task_queue.celery_app worker --loglevel=info
   ```

## 🛠 Platform Specific Configurations

- **YouTube**: Provide `YOUTUBE_API_KEY` in your `.env`.
- **Reddit**: Provide `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.
- **TikTok & Instagram**: Provide `TIKTOK_COOKIES_FILE` and `INSTAGRAM_COOKIES_FILE` pointing to a local `cookies.txt` file exported from your browser.
- **X/Twitter**: Run `twscrape` CLI to add accounts:
  ```bash
  twscrape add_accounts accounts.txt  # Format: username:password:email:email_password
  twscrape login_accounts
  ```

## 🧪 Testing

The repository uses `pytest` and `sqlite` memory databases for robust integration testing. Run tests with:
```bash
pytest tests/
```

## 📜 Architecture overview
- `app/api/`: FastAPI endpoint routing.
- `app/core/`: Settings, proxies, and rate limiting logic.
- `app/crawlers/`: Pluggable base architecture containing all the scrapers.
- `app/db/` & `app/models/`: SQLAlchemy connection & Declarative Base.
- `app/workers/`: Celery task definitions (entry point for distributed scrapers).

---
Developed by sqoder.
