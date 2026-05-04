"""
Tests for core modules: config, rate limiter, exceptions.
"""

import asyncio

import pytest

from app.core.config import Settings, get_settings
from app.core.exceptions import (APIKeyMissingError, ContentNotFoundError,
                                 CrawlerBaseError, CrawlError,
                                 MediaDownloadError, PlatformNotSupportedError,
                                 QuotaExhaustedError, RateLimitExceededError)
from app.core.rate_limiter import RateLimiter

# ---- Config Tests ----


class TestConfig:
    """Test configuration loading."""

    def test_default_settings(self):
        settings = Settings(
            _env_file=None,  # Don't load .env for tests
        )
        assert settings.app_name == "GlobalMediaCrawler"
        assert settings.debug is True
        assert settings.default_rate_limit == 30

    def test_settings_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_is_production(self):
        settings = Settings(app_env="production", _env_file=None)
        assert settings.is_production is True

        settings2 = Settings(app_env="development", _env_file=None)
        assert settings2.is_production is False

    def test_youtube_crawler_settings(self):
        settings = Settings(_env_file=None)
        # Check default values for new settings
        assert hasattr(settings, "youtube_cookies_file")
        assert settings.playwright_browser_count == 3


# ---- Exception Tests ----


class TestExceptions:
    """Test custom exception hierarchy."""

    def test_base_error(self):
        err = CrawlerBaseError("test error", platform="youtube")
        assert str(err) == "test error"
        assert err.platform == "youtube"

    def test_platform_not_supported(self):
        err = PlatformNotSupportedError("fakebook")
        assert "fakebook" in str(err)
        assert err.platform == "fakebook"

    def test_rate_limit_exceeded(self):
        err = RateLimitExceededError("reddit", retry_after=30)
        assert err.retry_after == 30
        assert "reddit" in str(err)

    def test_api_key_missing(self):
        err = APIKeyMissingError("youtube", "YOUTUBE_API_KEY")
        assert err.key_name == "YOUTUBE_API_KEY"

    def test_quota_exhausted(self):
        err = QuotaExhaustedError("youtube", quota_used=9500, quota_limit=10000)
        assert err.quota_used == 9500
        assert err.quota_limit == 10000

    def test_crawl_error(self):
        err = CrawlError("tiktok", "search", "timeout")
        assert err.operation == "search"
        assert err.reason == "timeout"

    def test_media_download_error(self):
        err = MediaDownloadError("https://example.com/video.mp4", "404")
        assert err.url == "https://example.com/video.mp4"

    def test_content_not_found(self):
        err = ContentNotFoundError("reddit", "post_123")
        assert err.identifier == "post_123"

    def test_exception_inheritance(self):
        """All custom exceptions should inherit from CrawlerBaseError."""
        assert issubclass(PlatformNotSupportedError, CrawlerBaseError)
        assert issubclass(RateLimitExceededError, CrawlerBaseError)
        assert issubclass(QuotaExhaustedError, CrawlerBaseError)
        assert issubclass(CrawlError, CrawlerBaseError)
        assert issubclass(MediaDownloadError, CrawlerBaseError)


# ---- Rate Limiter Tests ----


class TestRateLimiter:
    """Test the token-bucket rate limiter."""

    def test_configure(self):
        limiter = RateLimiter()
        limiter.configure("test", max_requests=10, period_seconds=60)
        assert limiter.get_remaining("test") == 10

    @pytest.mark.asyncio
    async def test_acquire_basic(self):
        limiter = RateLimiter()
        limiter.configure("test", max_requests=5, period_seconds=60)

        result = await limiter.acquire("test")
        assert result is True
        assert limiter.get_remaining("test") < 5

    @pytest.mark.asyncio
    async def test_acquire_unconfigured_platform(self):
        limiter = RateLimiter()
        # Unconfigured platforms should always pass
        result = await limiter.acquire("unconfigured")
        assert result is True

    def test_get_remaining_unconfigured(self):
        limiter = RateLimiter()
        assert limiter.get_remaining("nonexistent") is None

    @pytest.mark.asyncio
    async def test_acquire_multiple(self):
        limiter = RateLimiter()
        limiter.configure("test", max_requests=3, period_seconds=60)

        await limiter.acquire("test")
        await limiter.acquire("test")
        remaining = limiter.get_remaining("test")
        assert remaining < 2
