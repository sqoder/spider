"""
Crawler factory - creates platform-specific crawler instances.
"""

from typing import Type

from loguru import logger

from app.core.exceptions import PlatformNotSupportedError
from app.crawlers.base import BaseCrawler


class CrawlerFactory:
    """
    Factory pattern for creating platform-specific crawler instances.

    Usage:
        crawler = CrawlerFactory.create("youtube")
        results = await crawler.search("AI tools", limit=20)
    """

    _registry: dict[str, Type[BaseCrawler]] = {}

    @classmethod
    def register(cls, platform: str, crawler_class: Type[BaseCrawler]) -> None:
        """Register a crawler class for a platform."""
        cls._registry[platform.lower()] = crawler_class
        logger.debug(f"Registered crawler for platform: {platform}")

    @classmethod
    def create(cls, platform: str) -> BaseCrawler:
        """
        Create a crawler instance for the given platform.

        Args:
            platform: Platform name (youtube, reddit, etc.)

        Returns:
            An instance of a class inheriting from BaseCrawler

        Raises:
            PlatformNotSupportedError: If the platform is not registered
        """
        platform = platform.lower()
        if platform not in cls._registry:
            raise PlatformNotSupportedError(platform)

        # Special handling for YouTube smart fallback
        if platform == "youtube":
            from app.core.config import get_settings

            settings = get_settings()

            if settings.youtube_use_scraper:
                logger.info("Using YouTube visible-first scraper mode.")
                from app.crawlers.youtube.visible_crawler import VisibleYouTubeCrawler

                return VisibleYouTubeCrawler()

            if not settings.youtube_api_key:
                logger.info("Using yt-dlp YouTube crawler (no API key).")
                from app.crawlers.youtube.ytdlp_crawler import YtdlpYouTubeCrawler

                return YtdlpYouTubeCrawler()

        crawler_class = cls._registry[platform]
        logger.info(f"Creating crawler for platform: {platform}")
        return crawler_class()

    @classmethod
    def get_supported_platforms(cls) -> list[str]:
        """Get list of supported platform names."""
        return sorted(cls._registry.keys())

    @classmethod
    def is_supported(cls, platform: str) -> bool:
        """Check if a platform is supported."""
        return platform.lower() in cls._registry


def register_all_crawlers() -> None:
    """Register all available platform crawlers based on enabled_platforms config."""
    from app.core.config import get_settings

    settings = get_settings()
    enabled = {
        item.strip().lower() for item in settings.enabled_platforms.split(",") if item.strip()
    }

    if "youtube" in enabled:
        try:
            from app.core.config import get_settings

            settings = get_settings()

            if settings.youtube_use_scraper:
                from app.crawlers.youtube.visible_crawler import VisibleYouTubeCrawler

                CrawlerFactory.register("youtube", VisibleYouTubeCrawler)
                logger.info("Using YouTube visible-first scraper.")
            elif not settings.youtube_api_key:
                from app.crawlers.youtube.ytdlp_crawler import YtdlpYouTubeCrawler

                CrawlerFactory.register("youtube", YtdlpYouTubeCrawler)
                logger.info("YouTube API Key not found. Using yt-dlp crawler.")
            else:
                from app.crawlers.youtube.crawler import YouTubeCrawler

                CrawlerFactory.register("youtube", YouTubeCrawler)
                logger.info("Using YouTube API crawler.")
        except ImportError as e:
            logger.warning(f"YouTube crawler unavailable: {e}")

    if "reddit" in enabled:
        try:
            from app.crawlers.reddit.crawler import RedditCrawler

            CrawlerFactory.register("reddit", RedditCrawler)
        except ImportError as e:
            logger.warning(f"Reddit crawler unavailable: {e}")

    if "tiktok" in enabled:
        try:
            from app.crawlers.tiktok.crawler import TikTokCrawler

            CrawlerFactory.register("tiktok", TikTokCrawler)
        except ImportError as e:
            logger.warning(f"TikTok crawler unavailable: {e}")

    if "instagram" in enabled:
        try:
            from app.crawlers.instagram.crawler import InstagramCrawler

            CrawlerFactory.register("instagram", InstagramCrawler)
        except ImportError as e:
            logger.warning(f"Instagram crawler unavailable: {e}")

    if "x" in enabled or "twitter" in enabled:
        try:
            from app.crawlers.x.crawler import XCrawler

            CrawlerFactory.register("x", XCrawler)
        except ImportError as e:
            logger.warning(f"X/Twitter crawler unavailable: {e}")

    logger.info(f"Registered crawlers: {CrawlerFactory.get_supported_platforms()}")
