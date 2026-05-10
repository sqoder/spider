"""
Playwright-based crawler for YouTube.

Historically this was a standalone implementation that used Playwright+DOM
selectors to scrape YouTube. YouTube's front-end churns on those selectors
constantly (see git history for the 'h1.ytd-watch-metadata' / 'ytd-rich-
item-renderer' breakages), and VisibleYouTubeCrawler already does the same
job by reading ytInitialData from the HTML source, which is far more stable.

Rather than keep two parallel implementations in lock-step, this module is
now a thin delegation wrapper around VisibleYouTubeCrawler. The class name
is retained so existing imports, factory hooks, and quota-fallback paths
(YouTubeCrawler.get_comments falls back to PlaywrightYouTubeCrawler) keep
working without change.

If you need a pure-DOM path in the future, add it as a method of the
visible crawler instead — keep one source of truth for YouTube scraping.
"""

from loguru import logger

from youtube_crawler.base import BaseCrawler, CommentResult, CrawlResult
from youtube_crawler.visible_crawler import VisibleYouTubeCrawler


class PlaywrightYouTubeCrawler(BaseCrawler):
    """Backward-compatible shim that forwards to VisibleYouTubeCrawler."""

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self._inner = VisibleYouTubeCrawler()
        logger.debug(
            "[Playwright] PlaywrightYouTubeCrawler now delegates to VisibleYouTubeCrawler"
        )

    async def search(self, keyword: str, limit: int = 10) -> list[CrawlResult]:
        return await self._inner.search(keyword, limit=limit)

    async def get_user_posts(self, username: str, limit: int = 10) -> list[CrawlResult]:
        return await self._inner.get_user_posts(username, limit=limit)

    async def get_post_detail(self, url: str) -> CrawlResult:
        return await self._inner.get_post_detail(url)

    async def get_comments(self, post_id: str, limit: int = 10) -> list[CommentResult]:
        return await self._inner.get_comments(post_id, limit=limit)

    async def close(self) -> None:
        await self._inner.close()
