"""
YouTube crawler implementation.
Uses YouTube Data API for structured data and yt-dlp for media downloads.
"""

import re
from datetime import datetime
from typing import Optional

from loguru import logger

from app.core.config import get_settings
from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.youtube.api_client import YouTubeAPIClient
from app.crawlers.youtube.ytdlp_client import YtdlpClient


class YouTubeCrawler(BaseCrawler):
    """YouTube platform crawler."""

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.api = YouTubeAPIClient()
        self.ytdlp = YtdlpClient()

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """Search YouTube videos by keyword."""
        await self._rate_limit(cost=100)  # search.list costs 100 quota units
        logger.info(f"YouTube search: '{keyword}', limit={limit}")

        results = []
        page_token = None
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, 50)
            response = await self.api.search_videos(
                query=keyword,
                max_results=batch_size,
                page_token=page_token,
            )

            items = response.get("items", [])
            if not items:
                break

            # Get video IDs for detailed info
            video_ids = [
                item["id"]["videoId"] for item in items if item["id"].get("videoId")
            ]
            details_response = await self.api.get_video_details(video_ids)
            details_map = {
                item["id"]: item for item in details_response.get("items", [])
            }

            for item in items:
                video_id = item["id"].get("videoId")
                if not video_id:
                    continue

                detail = details_map.get(video_id, {})
                result = self._parse_video(video_id, item.get("snippet", {}), detail)
                results.append(result)

            remaining -= len(items)
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"YouTube search returned {len(results)} results")
        return results[:limit]

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get videos from a YouTube channel by username/handle."""
        await self._rate_limit()
        logger.info(f"YouTube user posts: '{username}', limit={limit}")

        # First, resolve username to channel ID
        channel_response = await self.api.get_channel_info(username=username)
        channels = channel_response.get("items", [])
        if not channels:
            logger.warning(f"YouTube channel not found: {username}")
            return []

        channel_id = channels[0]["id"]

        # Then search for channel videos
        results = []
        page_token = None
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, 50)
            response = await self.api.get_channel_videos(
                channel_id=channel_id,
                max_results=batch_size,
                page_token=page_token,
            )

            items = response.get("items", [])
            if not items:
                break

            video_ids = [
                item["id"]["videoId"] for item in items if item["id"].get("videoId")
            ]
            details_response = await self.api.get_video_details(video_ids)
            details_map = {
                item["id"]: item for item in details_response.get("items", [])
            }

            for item in items:
                video_id = item["id"].get("videoId")
                if not video_id:
                    continue
                detail = details_map.get(video_id, {})
                result = self._parse_video(video_id, item.get("snippet", {}), detail)
                results.append(result)

            remaining -= len(items)
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results[:limit]

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detailed info for a single YouTube video."""
        await self._rate_limit()

        video_id = self._extract_video_id(url)
        logger.info(f"YouTube video detail: {video_id}")

        # Get API details
        response = await self.api.get_video_details([video_id])
        items = response.get("items", [])
        if not items:
            # Fallback to yt-dlp for metadata
            logger.info("Falling back to yt-dlp for metadata extraction")
            return await self._get_detail_via_ytdlp(url)

        item = items[0]
        snippet = item.get("snippet", {})

        result = self._parse_video(video_id, snippet, item)

        # Enhance with yt-dlp metadata (formats, direct URLs)
        try:
            ytdlp_info = await self.ytdlp.extract_info(url)
            result.media = [
                {
                    "type": "video",
                    "url": url,
                    "duration": ytdlp_info.get("duration"),
                    "formats_available": len(ytdlp_info.get("formats", [])),
                }
            ]
        except Exception as e:
            logger.warning(f"yt-dlp metadata enhancement failed: {e}")

        return result

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Get comments for a YouTube video."""
        await self._rate_limit()
        logger.info(f"YouTube comments: {post_id}, limit={limit}")

        results = []
        page_token = None
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, 100)
            response = await self.api.get_comments(
                video_id=post_id,
                max_results=batch_size,
                page_token=page_token,
            )

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                top_comment = item["snippet"]["topLevelComment"]["snippet"]
                comment = CommentResult(
                    platform="youtube",
                    source_id=item["id"],
                    content=top_comment.get("textDisplay"),
                    author_name=top_comment.get("authorDisplayName"),
                    author_username=top_comment.get("authorChannelUrl", "").split("/")[
                        -1
                    ],
                    author_id=top_comment.get("authorChannelId", {}).get("value"),
                    like_count=top_comment.get("likeCount", 0),
                    reply_count=item["snippet"].get("totalReplyCount", 0),
                    published_at=self._parse_datetime(top_comment.get("publishedAt")),
                    raw=item,
                )
                results.append(comment)

            remaining -= len(items)
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results[:limit]

    # ---- Private helpers ----

    def _parse_video(self, video_id: str, snippet: dict, detail: dict) -> CrawlResult:
        """Parse YouTube API response into a CrawlResult."""
        statistics = detail.get("statistics", {})
        content_details = detail.get("contentDetails", {})

        return CrawlResult(
            platform="youtube",
            source_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=snippet.get("title"),
            content=snippet.get("description"),
            content_type="video",
            author_id=snippet.get("channelId"),
            author_name=snippet.get("channelTitle"),
            author_username=snippet.get("channelId"),
            author_url=f"https://www.youtube.com/channel/{snippet.get('channelId', '')}",
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0)),
            view_count=int(statistics.get("viewCount", 0)),
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url"),
            media=[
                {
                    "type": "video",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": content_details.get("duration"),
                    "thumbnail_url": snippet.get("thumbnails", {})
                    .get("high", {})
                    .get("url"),
                }
            ],
            published_at=self._parse_datetime(snippet.get("publishedAt")),
            raw=detail if detail else {"snippet": snippet},
        )

    async def _get_detail_via_ytdlp(self, url: str) -> CrawlResult:
        """Fallback: get video details using yt-dlp."""
        info = await self.ytdlp.extract_info(url)

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
            media=[
                {
                    "type": "video",
                    "url": url,
                    "duration": info.get("duration"),
                    "formats_available": len(info.get("formats", [])),
                }
            ],
            published_at=self._parse_datetime(info.get("upload_date")),
            raw=info,
        )

    @staticmethod
    def _extract_video_id(url: str) -> str:
        """Extract video ID from various YouTube URL formats."""
        patterns = [
            r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:embed/)([a-zA-Z0-9_-]{11})",
            r"(?:shorts/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # If it looks like a bare video ID
        if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
            return url

        raise ValueError(f"Cannot extract video ID from URL: {url}")

    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        """Parse various datetime formats from YouTube."""
        if not dt_str:
            return None
        try:
            # ISO 8601 format from API
            if "T" in dt_str:
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            # YYYYMMDD format from yt-dlp
            if len(dt_str) == 8 and dt_str.isdigit():
                return datetime.strptime(dt_str, "%Y%m%d")
        except (ValueError, TypeError):
            pass
        return None

    async def close(self) -> None:
        """Cleanup resources."""
        await self.api.close()
