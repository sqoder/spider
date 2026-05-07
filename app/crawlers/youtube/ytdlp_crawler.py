"""
yt-dlp based YouTube Crawler.
Used as a stable fallback when no API key is provided.
"""

from typing import Optional
from datetime import datetime
from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.youtube.ytdlp_client import YtdlpClient


def _parse_upload_date(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse YYYYMMDD strings returned by yt-dlp into datetime objects."""
    if not dt_str:
        return None
    try:
        if len(dt_str) == 8 and dt_str.isdigit():
            return datetime.strptime(dt_str, "%Y%m%d")
    except (ValueError, TypeError):
        pass
    return None

class YtdlpYouTubeCrawler(BaseCrawler):
    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.ytdlp = YtdlpClient()
        self._visible_crawler = None

    def _get_visible_crawler(self):
        if self._visible_crawler is None:
            from app.crawlers.youtube.visible_crawler import VisibleYouTubeCrawler
            self._visible_crawler = VisibleYouTubeCrawler()
        return self._visible_crawler

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        await self._rate_limit()
        logger.info(f"[yt-dlp] Searching YouTube for: {keyword}")

        search_query = f"ytsearch{limit}:{keyword}"
        items = await self.ytdlp.extract_multiple_info(search_query)
        
        results = []
        for info in items:
            results.append(self._parse_info(info))
            
        return results

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        await self._rate_limit()
        logger.info(f"[yt-dlp] Getting channel videos for: {username}")
        url = f"https://www.youtube.com/@{username}/videos"
        items = await self.ytdlp.extract_multiple_info(url, limit=limit)
        return [self._parse_info(info) for info in items]

    async def get_post_detail(self, url: str) -> CrawlResult:
        await self._rate_limit()
        logger.info(f"[yt-dlp] Getting video detail: {url}")
        info = await self.ytdlp.extract_info(url)
        return self._parse_info(info)

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Fetch comments using the visible-first crawler's multi-tier strategy."""
        await self._rate_limit()
        logger.info(f"[Scraper] Fetching comments for {post_id} using visible helper")
        return await self._get_visible_crawler().get_comments(post_id, limit)

    def _parse_info(self, info: dict) -> CrawlResult:
        url = info.get("original_url") or info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id')}"
        
        # Extract chapters
        chapters = []
        for chapter in info.get("chapters") or []:
            chapters.append({
                "start_time": chapter.get("start_time"),
                "end_time": chapter.get("end_time"),
                "title": chapter.get("title")
            })

        return CrawlResult(
            platform="youtube",
            source_id=info.get("id", ""),
            url=url,
            title=info.get("title"),
            content=info.get("description"),
            content_type="video",
            author_id=info.get("channel_id"),
            author_name=info.get("channel"),
            author_username=info.get("uploader_id"),
            author_url=info.get("channel_url"),
            like_count=info.get("like_count", 0) or 0,
            comment_count=info.get("comment_count", 0) or 0,
            view_count=info.get("view_count", 0) or 0,
            thumbnail_url=info.get("thumbnail"),
            author_avatar=info.get("avatar") or info.get("channel_thumbnail") or info.get("channel_avatar"),
            tags=info.get("tags", []),
            media=[
                {
                    "type": "video",
                    "url": url,
                    "duration": info.get("duration"),
                    "formats_available": len(info.get("formats", [])),
                    "chapters": chapters,
                    "categories": info.get("categories", []),
                    "subtitles": list(info.get("subtitles", {}).keys()) + list(info.get("automatic_captions", {}).keys())
                }
            ],
            published_at=_parse_upload_date(info.get("upload_date")),
            raw=info,
        )

    async def close(self) -> None:
        if self._visible_crawler:
            await self._visible_crawler.close()
