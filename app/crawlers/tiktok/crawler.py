"""
TikTok crawler implementation.
Uses gallery-dl for metadata and yt-dlp for video downloads.
First phase: user videos, single video detail, video download, basic metadata.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.tiktok.gallerydl_client import GalleryDLClient


class TikTokCrawler(BaseCrawler):
    """TikTok platform crawler."""

    platform = "tiktok"

    def __init__(self):
        super().__init__()
        self.gallery_dl = GalleryDLClient(platform="tiktok")

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search TikTok videos by keyword.
        Note: TikTok search via gallery-dl is limited. Uses tag/hashtag search as fallback.
        """
        await self._rate_limit()
        logger.info(f"TikTok search: '{keyword}', limit={limit}")

        # Try hashtag search via gallery-dl
        tag = keyword.replace(" ", "").replace("#", "")
        url = f"https://www.tiktok.com/tag/{tag}"

        try:
            items = await self.gallery_dl.extract_metadata(url)
            results = []
            for item in items[:limit]:
                result = self._parse_tiktok_item(item)
                if result:
                    results.append(result)
            return results
        except Exception as e:
            logger.warning(f"TikTok search fallback failed: {e}")
            return []

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get videos from a TikTok user's profile."""
        await self._rate_limit()
        logger.info(f"TikTok user posts: '{username}', limit={limit}")

        username = username.lstrip("@")
        items = await self.gallery_dl.get_user_content(username, limit=limit)

        results = []
        for item in items:
            result = self._parse_tiktok_item(item)
            if result:
                results.append(result)

        logger.info(f"TikTok user posts returned {len(results)} results")
        return results[:limit]

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detailed info for a single TikTok video."""
        await self._rate_limit()
        logger.info(f"TikTok post detail: {url}")

        items = await self.gallery_dl.extract_metadata(url)
        if not items:
            # Fallback to yt-dlp
            return await self._get_detail_via_ytdlp(url)

        result = self._parse_tiktok_item(items[0])
        if result:
            return result

        return await self._get_detail_via_ytdlp(url)

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """
        Get comments for a TikTok video.
        Note: Comments are not easily accessible without API. Returns empty for now.
        """
        logger.warning("TikTok comments are not supported in Phase 1")
        return []

    # ---- Private helpers ----

    def _parse_tiktok_item(self, data: dict) -> Optional[CrawlResult]:
        """Parse gallery-dl TikTok metadata into a CrawlResult."""
        if not data:
            return None

        video_id = str(data.get("id", data.get("aweme_id", "")))
        if not video_id:
            return None

        author_info = data.get("author", {})
        if isinstance(author_info, str):
            author_info = {"nickname": author_info}

        stats = data.get("stats", data.get("statistics", {}))

        # Build media info
        media = []
        video_url = data.get("url") or data.get("video_url")
        if video_url:
            media.append({
                "type": "video",
                "url": video_url,
                "duration": data.get("duration"),
            })

        # Build post URL
        username = author_info.get("uniqueId", author_info.get("unique_id", ""))
        post_url = data.get("webpage_url") or f"https://www.tiktok.com/@{username}/video/{video_id}"

        published_at = None
        create_time = data.get("createTime", data.get("create_time"))
        if create_time:
            try:
                published_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        return CrawlResult(
            platform="tiktok",
            source_id=video_id,
            url=post_url,
            title=data.get("desc", data.get("description", "")),
            content=data.get("desc", data.get("description", "")),
            content_type="video",
            author_id=str(author_info.get("id", "")),
            author_name=author_info.get("nickname", ""),
            author_username=author_info.get("uniqueId", author_info.get("unique_id", "")),
            author_url=f"https://www.tiktok.com/@{username}" if username else None,
            like_count=stats.get("diggCount", stats.get("digg_count", 0)) or 0,
            comment_count=stats.get("commentCount", stats.get("comment_count", 0)) or 0,
            share_count=stats.get("shareCount", stats.get("share_count", 0)) or 0,
            view_count=stats.get("playCount", stats.get("play_count", 0)) or 0,
            media=media,
            thumbnail_url=data.get("cover", data.get("thumbnail")),
            published_at=published_at,
            raw=data,
        )

    async def _get_detail_via_ytdlp(self, url: str) -> CrawlResult:
        """Fallback: get TikTok video details using yt-dlp."""
        import asyncio
        import json

        cmd = ["yt-dlp", "--dump-json", "--no-download", url]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

        if process.returncode != 0:
            raise ValueError(f"yt-dlp failed for {url}")

        info = json.loads(stdout.decode("utf-8"))

        return CrawlResult(
            platform="tiktok",
            source_id=info.get("id", ""),
            url=url,
            title=info.get("title", ""),
            content=info.get("description", ""),
            content_type="video",
            author_id=info.get("uploader_id", ""),
            author_name=info.get("uploader", ""),
            author_username=info.get("uploader_id", ""),
            author_url=info.get("uploader_url"),
            like_count=info.get("like_count", 0) or 0,
            comment_count=info.get("comment_count", 0) or 0,
            view_count=info.get("view_count", 0) or 0,
            media=[{
                "type": "video",
                "url": url,
                "duration": info.get("duration"),
            }],
            published_at=None,
            raw=info,
        )

    async def close(self) -> None:
        pass
