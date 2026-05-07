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
from app.crawlers.tiktok.playwright_client import PlaywrightTikTokClient


class TikTokCrawler(BaseCrawler):
    """TikTok platform crawler."""

    platform = "tiktok"

    def __init__(self):
        super().__init__()
        self.gallery_dl = GalleryDLClient(platform="tiktok")
        self.playwright = PlaywrightTikTokClient()

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search TikTok videos by keyword using Playwright interception to bypass anti-crawler.
        """
        await self._rate_limit()
        logger.info(f"TikTok search: '{keyword}', limit={limit}")

        items = await self.playwright.search_keyword(keyword, limit=limit)
        results = []
        for item in items:
            parsed = self._parse_playwright_item(item)
            if parsed:
                results.append(parsed)

        return results

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get videos from a TikTok user's profile using yt-dlp."""
        await self._rate_limit()
        logger.info(f"TikTok user posts: '{username}', limit={limit}")

        username = username.lstrip("@")
        url = f"https://www.tiktok.com/@{username}"

        import asyncio
        import json

        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--playlist-end",
            str(limit),
            "--ignore-errors",
            url,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            results = []
            for line in stdout.decode("utf-8").split("\n"):
                line = line.strip()
                if line:
                    try:
                        info = json.loads(line)
                        results.append(self._parse_ytdlp_item(info))
                    except json.JSONDecodeError:
                        continue

            logger.info(f"TikTok user posts returned {len(results)} results")
            return results[:limit]
        except Exception as e:
            logger.warning(f"TikTok user posts yt-dlp failed: {e}")
            return []

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
        Get comments for a TikTok video using Playwright.
        """
        await self._rate_limit()

        username = "tiktok"
        video_id = post_id
        if ":" in post_id:
            username, video_id = post_id.split(":", 1)

        logger.info(f"TikTok get comments for video: {video_id} by @{username}")

        raw_comments = await self.playwright.get_comments(video_id, limit=limit, username=username)
        results = []
        for c in raw_comments:
            parsed = self._parse_playwright_comment(c, post_id)
            if parsed:
                results.append(parsed)

        return results

    # ---- Private helpers ----

    def _parse_playwright_item(self, data: dict) -> Optional[CrawlResult]:
        if not data:
            return None

        video_id = str(data.get("id", ""))
        if not video_id:
            return None

        author = data.get("author", {})
        stats = data.get("stats", {})
        video_info = data.get("video", {})

        username = author.get("uniqueId", "")
        post_url = f"https://www.tiktok.com/@{username}/video/{video_id}"

        video_url = video_info.get("playAddr") or video_info.get("downloadAddr") or post_url

        published_at = None
        create_time = data.get("createTime")
        if create_time:
            try:
                published_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        return CrawlResult(
            platform="tiktok",
            source_id=video_id,
            url=post_url,
            title=data.get("desc", ""),
            content=data.get("desc", ""),
            content_type="video",
            author_id=str(author.get("id", "")),
            author_name=author.get("nickname", ""),
            author_username=username,
            author_url=f"https://www.tiktok.com/@{username}" if username else None,
            like_count=stats.get("diggCount", 0),
            comment_count=stats.get("commentCount", 0),
            share_count=stats.get("shareCount", 0),
            view_count=stats.get("playCount", 0),
            media=[
                {
                    "type": "video",
                    "url": video_url,
                    "duration": video_info.get("duration", 0),
                }
            ],
            thumbnail_url=video_info.get("cover"),
            published_at=published_at,
            raw=data,
        )

    def _parse_playwright_comment(self, data: dict, post_id: str) -> Optional[CommentResult]:
        if not data:
            return None

        cid = str(data.get("cid", ""))
        if not cid:
            return None

        user = data.get("user", {})

        published_at = None
        create_time = data.get("create_time")
        if create_time:
            try:
                published_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        return CommentResult(
            platform="tiktok",
            comment_id=cid,
            post_id=post_id,
            parent_comment_id=str(data.get("reply_id", ""))
            if data.get("reply_id") != "0"
            else None,
            content=data.get("text", ""),
            author_id=str(user.get("uid", "")),
            author_name=user.get("nickname", ""),
            author_username=user.get("unique_id", ""),
            author_avatar=user.get("avatar_thumb", {}).get("url_list", [""])[0]
            if user.get("avatar_thumb")
            else None,
            like_count=data.get("digg_count", 0),
            reply_count=data.get("reply_comment_total", 0),
            published_at=published_at,
            raw=data,
        )

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
            media.append(
                {
                    "type": "video",
                    "url": video_url,
                    "duration": data.get("duration"),
                }
            )

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

    def _parse_ytdlp_item(self, info: dict) -> CrawlResult:
        """Parse yt-dlp json info into CrawlResult."""
        url = info.get("webpage_url") or info.get("original_url") or ""

        published_at = None
        ts = info.get("timestamp")
        if ts:
            try:
                published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

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
            share_count=info.get("repost_count", 0) or 0,
            view_count=info.get("view_count", 0) or 0,
            media=[
                {
                    "type": "video",
                    "url": url,
                    "duration": info.get("duration"),
                }
            ],
            thumbnail_url=info.get("thumbnail"),
            published_at=published_at,
            raw=info,
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
        return self._parse_ytdlp_item(info)

    async def close(self) -> None:
        await self.playwright.close()
