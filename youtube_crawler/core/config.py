"""
Application configuration management.
Uses pydantic-settings to load from environment variables and .env file.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

import crawler_config as _cfg


class Settings(BaseSettings):
    """Global application settings loaded from environment variables."""

    # Unique timestamp for each execution run
    run_timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Mode ----
    # simple_mode: disables Celery/Redis dependency for local dev
    simple_mode: bool = _cfg.SIMPLE_MODE
    # Data directory for SQLite DB and file storage
    data_dir: str = _cfg.DATA_DIR

    # ---- Storage Options ----
    # Supported: csv, db, json, jsonl, sqlite, excel, postgres
    save_data_option: str = _cfg.SAVE_FORMAT
    save_data_path: str = _cfg.SAVE_PATH
    # Subdirectory name under {platform}/ (defaults to the format name, e.g. "csv")
    save_data_subdir: str | None = None

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ---- Application ----
    app_name: str = "GlobalMediaCrawler"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "DEBUG"

    cors_origins: str = "http://localhost:3000"

    auto_create_tables: bool = False
    enabled_platforms: str = ",".join(_cfg.ENABLED_PLATFORMS)

    # ---- Database ----
    database_url: str = _cfg.DATABASE_URI
    database_echo: bool = False

    # ---- Redis ----
    redis_url: str = _cfg.REDIS_URL if hasattr(_cfg, "REDIS_URL") else "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600  # seconds

    # ---- Celery ----
    celery_broker_url: str = _cfg.CELERY_BROKER_URL if hasattr(_cfg, "CELERY_BROKER_URL") else "redis://localhost:6379/1"
    celery_result_backend: str = _cfg.CELERY_RESULT_BACKEND if hasattr(_cfg, "CELERY_RESULT_BACKEND") else "redis://localhost:6379/2"

    # ---- Media Storage ----
    media_storage_path: str = _cfg.SAVE_PATH
    media_max_size_mb: int = 500
    media_quality: int = _cfg.MEDIA_QUALITY
    media_types: str = ",".join(_cfg.MEDIA_TYPES)

    # ---- YouTube ----
    # Secrets default to None; set via .env (YOUTUBE_API_KEY) to override.
    youtube_api_key: str | None = None
    youtube_daily_quota: int = _cfg.YOUTUBE_DAILY_QUOTA
    youtube_use_scraper: bool = _cfg.YOUTUBE_USE_SCRAPER
    youtube_cookies_file: str | None = _cfg.YOUTUBE_COOKIES_FILE
    playwright_browser_count: int = _cfg.CONCURRENT_LIMIT
    playwright_headless: bool = True

    # ---- Reddit ----
    # Secrets default to None; set via .env (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET).
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = _cfg.REDDIT_USER_AGENT

    # ---- TikTok ----
    tiktok_cookies_file: str | None = _cfg.TIKTOK_COOKIES_FILE

    # ---- Instagram ----
    instagram_cookies_file: str | None = _cfg.INSTAGRAM_COOKIES_FILE

    # ---- X / Twitter ----
    x_accounts_file: str | None = _cfg.X_ACCOUNTS_FILE

    # ---- Rate Limiting ----
    request_delay: float = _cfg.REQUEST_DELAY if hasattr(_cfg, "REQUEST_DELAY") else 0.2
    max_retries: int = _cfg.MAX_RETRIES if hasattr(_cfg, "MAX_RETRIES") else 3
    default_rate_limit: int = _cfg.DEFAULT_RATE_LIMIT
    default_rate_period: int = _cfg.DEFAULT_RATE_PERIOD
    youtube_rate_limit: int = _cfg.YOUTUBE_RATE_LIMIT
    youtube_rate_period: int = _cfg.YOUTUBE_RATE_PERIOD
    reddit_rate_limit: int = _cfg.REDDIT_RATE_LIMIT
    reddit_rate_period: int = _cfg.REDDIT_RATE_PERIOD
    tiktok_rate_limit: int = _cfg.TIKTOK_RATE_LIMIT
    tiktok_rate_period: int = _cfg.TIKTOK_RATE_PERIOD

    # ---- Crawl Controls ----
    crawl_mode: str = _cfg.CRAWL_MODE
    crawl_keyword: str = _cfg.KEYWORDS[0] if isinstance(_cfg.KEYWORDS, list) and _cfg.KEYWORDS else str(_cfg.KEYWORDS)
    crawl_urls: str = ",".join(_cfg.URLS)
    crawl_user_handle: str = _cfg.USER_HANDLE
    crawl_user_post_limit: int = _cfg.USER_POST_LIMIT
    crawl_search_limit: int = _cfg.LIMIT
    crawl_comments_enabled: bool = _cfg.DOWNLOAD_COMMENTS
    crawl_comments_count: int = _cfg.COMMENTS_LIMIT
    crawl_comments_sort: str = _cfg.COMMENTS_SORT
    crawl_comments_include_replies: bool = _cfg.DOWNLOAD_REPLIES
    crawl_media_enabled: bool = _cfg.DOWNLOAD_MEDIA

    # ---- Proxy ----
    proxy_url: str | None = _cfg.PROXY_URL if _cfg.PROXY_URL else None
    proxy_rotation: bool = _cfg.PROXY_ROTATION


    @property
    def media_path(self) -> Path:
        """Return the media storage path as a Path object, creating it if needed."""
        path = Path(self.media_storage_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings (singleton)."""
    return Settings()
