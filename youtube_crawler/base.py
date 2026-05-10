"""
Base crawler abstract class.
All platform-specific crawlers must inherit from BaseCrawler and implement its methods.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from youtube_crawler.core.rate_limiter import rate_limiter


@dataclass
class CrawlResult:
    """Unified result container returned by all crawler methods."""

    platform: str
    source_id: str
    url: str | None = None
    title: str | None = None
    content: str | None = None
    content_type: str | None = None  # video, image, text, reel, etc.

    # Author info
    author_id: str | None = None
    author_name: str | None = None
    author_username: str | None = None
    author_url: str | None = None
    author_avatar: str | None = None

    # Metrics
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    view_count: int = 0

    # Media
    media: list[dict] = field(default_factory=list)
    thumbnail_url: str | None = None

    # Extra Metadata
    tags: list[str] = field(default_factory=list)
    subtitles: list[dict] = field(default_factory=list)

    # Timestamps
    published_at: datetime | None = None

    # Raw API response
    raw: dict[str, Any] = field(default_factory=dict)
    visible_data: dict[str, Any] = field(default_factory=dict)
    raw_sources: dict[str, Any] = field(default_factory=dict)
    capture_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to the unified data format."""
        return {
            "platform": self.platform,
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "content_type": self.content_type,
            "author": {
                "id": self.author_id,
                "name": self.author_name,
                "username": self.author_username,
                "url": self.author_url,
                "avatar": self.author_avatar,
            },
            "metrics": {
                "like_count": self.like_count,
                "comment_count": self.comment_count,
                "share_count": self.share_count,
                "view_count": self.view_count,
            },
            "media": self.media,
            "tags": self.tags,
            "subtitles": self.subtitles,
            "published_at": (self.published_at.isoformat() if self.published_at else None),
            "raw": self.raw,
            "visible_data": self.visible_data,
            "raw_sources": self.raw_sources,
            "capture_meta": self.capture_meta,
        }


@dataclass
class CommentResult:
    """Unified comment result container."""

    platform: str
    source_id: str
    content: str | None = None
    author_name: str | None = None
    author_username: str | None = None
    author_id: str | None = None
    like_count: int = 0
    reply_count: int = 0
    parent_comment_id: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    visible_data: dict[str, Any] = field(default_factory=dict)
    raw_sources: dict[str, Any] = field(default_factory=dict)
    capture_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "source_id": self.source_id,
            "content": self.content,
            "author_name": self.author_name,
            "author_username": self.author_username,
            "author_id": self.author_id,
            "like_count": self.like_count,
            "reply_count": self.reply_count,
            "parent_comment_id": self.parent_comment_id,
            "published_at": (self.published_at.isoformat() if self.published_at else None),
            "raw": self.raw,
            "visible_data": self.visible_data,
            "raw_sources": self.raw_sources,
            "capture_meta": self.capture_meta,
        }


class BaseCrawler(ABC):
    """
    Abstract base class for all platform crawlers.

    Each platform must implement the four core methods:
    - search: Search for content by keyword
    - get_user_posts: Get posts from a specific user
    - get_post_detail: Get detailed info for a single post
    - get_comments: Get comments for a post
    """

    # Subclasses must set this
    platform: str = ""

    def __init__(self):
        if not self.platform:
            raise ValueError("Platform name must be set in subclass")
        logger.info(f"Initializing {self.platform} crawler")

    async def _rate_limit(self, cost: int = 1) -> None:
        """Apply rate limiting before making a request."""
        # 1. Distributed/Local Token Bucket Rate Limiting
        await rate_limiter.acquire(self.platform, cost=cost)
        
        # 2. Fixed Politeness Delay (from crawler_config.py)
        from youtube_crawler.core.config import get_settings
        settings = get_settings()
        if settings.request_delay > 0:
            await asyncio.sleep(settings.request_delay)

    @abstractmethod
    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search for content on the platform.

        Args:
            keyword: Search query string
            limit: Maximum number of results to return

        Returns:
            List of CrawlResult objects
        """
        ...

    @abstractmethod
    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """
        Get posts/content from a specific user.

        Args:
            username: Platform username or handle
            limit: Maximum number of results to return

        Returns:
            List of CrawlResult objects
        """
        ...

    @abstractmethod
    async def get_post_detail(self, url: str) -> CrawlResult:
        """
        Get detailed information for a single post/content.

        Args:
            url: URL of the content

        Returns:
            CrawlResult object
        """
        ...

    @abstractmethod
    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """
        Get comments for a specific post.

        Args:
            post_id: Platform-specific post/content identifier
            limit: Maximum number of comments to return

        Returns:
            List of CommentResult objects
        """
        ...

    async def close(self) -> None:
        """Cleanup resources. Override in subclasses if needed."""
        logger.debug(f"Closing {self.platform} crawler")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(platform={self.platform})>"
