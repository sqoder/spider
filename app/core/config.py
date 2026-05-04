"""
Application configuration management.
Uses pydantic-settings to load from environment variables and .env file.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Mode ----
    # simple_mode: disables Celery/Redis dependency for local dev
    simple_mode: bool = True
    # Data directory for SQLite DB and file storage
    data_dir: str = "data"

    # ---- Storage Options ----
    # Supported: csv, db, json, jsonl, sqlite, excel, postgres
    save_data_option: str = "jsonl"
    save_data_path: str = "data"
    # Subdirectory name under {platform}/ (defaults to the format name, e.g. "csv")
    save_data_subdir: Optional[str] = None

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
    enabled_platforms: str = "youtube,reddit"

    # ---- Database ----
    database_url: str = (
        "postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler"
    )
    database_echo: bool = False

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600  # seconds

    # ---- Celery ----
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ---- Media Storage ----
    media_storage_path: str = "./output"
    media_max_size_mb: int = 500

    # ---- YouTube ----
    youtube_api_key: Optional[str] = None
    youtube_daily_quota: int = 10000
    youtube_use_scraper: bool = True  # Default to True for "native crawler" preference
    youtube_cookies_file: Optional[str] = None
    playwright_browser_count: int = 3

    # ---- Reddit ----
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    reddit_user_agent: str = "GlobalMediaCrawler/1.0"

    # ---- TikTok ----
    tiktok_cookies_file: Optional[str] = None

    # ---- Instagram ----
    instagram_cookies_file: Optional[str] = None

    # ---- X / Twitter ----
    x_accounts_file: Optional[str] = None

    # ---- Rate Limiting ----
    default_rate_limit: int = 30
    default_rate_period: int = 60
    youtube_rate_limit: int = 50
    youtube_rate_period: int = 60
    reddit_rate_limit: int = 90
    reddit_rate_period: int = 60
    tiktok_rate_limit: int = 20
    tiktok_rate_period: int = 60

    # ---- Crawl Controls ----
    crawl_search_limit: int = 10
    crawl_comments_enabled: bool = True
    crawl_comments_count: int = 50
    crawl_comments_include_replies: bool = False
    crawl_media_enabled: bool = True

    # ---- Proxy ----
    proxy_url: Optional[str] = None
    proxy_rotation: bool = False

    @property
    def media_path(self) -> Path:
        """Return the media storage path as a Path object, creating it if needed."""
        path = Path(self.media_storage_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings (singleton)."""
    return Settings()
