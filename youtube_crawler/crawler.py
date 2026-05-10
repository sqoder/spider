"""
YouTube crawler implementation.
Uses YouTube Data API for structured data and yt-dlp for media downloads.
"""

import re
from datetime import UTC, datetime

from loguru import logger

from youtube_crawler.core.exceptions import CrawlError, NetworkError, ParseError, QuotaExhaustedError
from youtube_crawler.base import BaseCrawler, CommentResult, CrawlResult
from youtube_crawler.api_client import YouTubeAPIClient
from youtube_crawler.ytdlp_client import YtdlpClient


class YouTubeCrawler(BaseCrawler):
    """YouTube platform crawler."""

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.api = YouTubeAPIClient()
        self.ytdlp = YtdlpClient()
        self._visible_crawler = None

    async def _get_visible_crawler(self):
        """Lazy initialization of the visible-first crawler for fallbacks."""
        if self._visible_crawler is None:
            from youtube_crawler.visible_crawler import VisibleYouTubeCrawler
            self._visible_crawler = VisibleYouTubeCrawler()
        return self._visible_crawler

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """Search YouTube videos by keyword with quota fallback and time-slicing for massive data retrieval."""
        try:
            logger.info(f"YouTube search: '{keyword}', limit={limit}")

            if limit <= 100:
                return await self._search_batch(keyword, limit)

            # Time-sliced search for high-concurrency / massive data ingestion (bypasses 500-1000 item limit)
            from datetime import timedelta
            now = datetime.now(UTC)

            # Slice into weekly segments (7 days) going backwards in time
            slice_days = 7
            current_end = now
            total_slices = 24  # Look back up to ~6 months

            results: list[CrawlResult] = []
            seen_ids = set()

            for _ in range(total_slices):
                if len(results) >= limit:
                    break

                current_start = current_end - timedelta(days=slice_days)
                published_after = current_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                published_before = current_end.strftime("%Y-%m-%dT%H:%M:%SZ")

                logger.info(f"[YouTube Slicer] Searching slice {published_after} to {published_before}")

                slice_limit = min(limit - len(results), 500)
                slice_results = await self._search_batch(
                    keyword,
                    slice_limit,
                    published_after=published_after,
                    published_before=published_before,
                )

                for res in slice_results:
                    if res.source_id not in seen_ids:
                        results.append(res)
                        seen_ids.add(res.source_id)

                current_end = current_start

                if not slice_results:
                    break

            logger.info(f"[YouTube Slicer] Completed search, gathered {len(results)} total results (deduplicated)")
            return results[:limit]

        except QuotaExhaustedError:
            logger.warning("YouTube API Quota exhausted! Falling back to yt-dlp for search.")
            from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler

            crawler = YtdlpYouTubeCrawler()
            return await crawler.search(keyword, limit)

    async def _search_batch(self, keyword: str, limit: int, **kwargs) -> list[CrawlResult]:
        """Perform a single standard search batch with pagination.

        On quota exhaustion, re-raises so the caller can fall back to yt-dlp.
        On transient network/parse errors, logs and returns what was collected
        so far (caller treats an empty result as "no more data" only when it
        means that — for the slicing loop, partial results are still useful).
        """
        results: list[CrawlResult] = []
        page_token = None
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, 50)
            try:
                response = await self.api.search_videos(
                    query=keyword,
                    max_results=batch_size,
                    page_token=page_token,
                    **kwargs,
                )

                items = response.get("items", [])
                if not items:
                    break

                # Get video IDs for detailed info. Use .get() so a malformed
                # item with no id.videoId doesn't crash the whole batch.
                video_ids = [
                    item.get("id", {}).get("videoId")
                    for item in items
                    if item.get("id", {}).get("videoId")
                ]
                details_response = await self.api.get_video_details(video_ids)
                details_map = {item["id"]: item for item in details_response.get("items", [])}

                for item in items:
                    video_id = item.get("id", {}).get("videoId")
                    if not video_id:
                        continue

                    detail = details_map.get(video_id, {})
                    result = self._parse_video(video_id, item.get("snippet", {}), detail)
                    results.append(result)

                # Use collected-result count, not page-item count: an "items"
                # batch may contain entries we skipped (no videoId), and the
                # previous `remaining -= len(items)` over-counted those.
                remaining = limit - len(results)
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            except QuotaExhaustedError:
                # Let the outer search() handler trigger the yt-dlp fallback.
                raise
            except (NetworkError, ParseError, CrawlError) as e:
                logger.error(
                    f"[YouTube Slicer] Search batch aborted after {len(results)} results: {e}"
                )
                break
            except Exception:
                # Unexpected / programming error — don't swallow it.
                logger.exception(f"[YouTube Slicer] Search batch raised unexpectedly after {len(results)} results")
                raise

        return results

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get videos from a YouTube channel by username/handle."""
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
            # B4: Rate limit before each batch call
            await self._rate_limit(cost=100)
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
                item.get("id", {}).get("videoId")
                for item in items
                if item.get("id", {}).get("videoId")
            ]
            details_response = await self.api.get_video_details(video_ids)
            details_map = {item["id"]: item for item in details_response.get("items", [])}

            for item in items:
                video_id = item.get("id", {}).get("videoId")
                if not video_id:
                    continue
                detail = details_map.get(video_id, {})
                result = self._parse_video(video_id, item.get("snippet", {}), detail)
                results.append(result)

            remaining = limit - len(results)
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

        # Enhance with yt-dlp metadata (formats, direct URLs). yt-dlp returns
        # duration as int seconds — keep the unit consistent with _parse_video.
        try:
            ytdlp_info = await self.ytdlp.extract_info(url)
            result.media = [
                {
                    "type": "video",
                    "url": url,
                    "duration": ytdlp_info.get("duration"),
                    "duration_iso": result.media[0].get("duration_iso") if result.media else None,
                    "formats_available": len(ytdlp_info.get("formats", [])),
                }
            ]
        except Exception as e:
            logger.warning(f"yt-dlp metadata enhancement failed: {e}")

        return result

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Get comments for a YouTube video with quota fallback."""
        try:
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
                    snippet_wrap = item.get("snippet") or {}
                    top_comment_node = snippet_wrap.get("topLevelComment") or {}
                    top_comment = top_comment_node.get("snippet") or {}
                    comment_id = item.get("id")
                    if not comment_id or not top_comment:
                        # Partial/deleted/hidden items occasionally appear; skip
                        # rather than killing the whole page of comments.
                        logger.debug(f"Skipping malformed comment item: id={comment_id!r}")
                        continue

                    # Add top-level comment
                    comment = CommentResult(
                        platform="youtube",
                        source_id=comment_id,
                        content=top_comment.get("textDisplay"),
                        author_name=top_comment.get("authorDisplayName"),
                        author_username=self._channel_handle_from_url(
                            top_comment.get("authorChannelUrl", "")
                        ),
                        author_id=top_comment.get("authorChannelId", {}).get("value"),
                        like_count=top_comment.get("likeCount", 0),
                        reply_count=snippet_wrap.get("totalReplyCount", 0),
                        published_at=self._parse_datetime(top_comment.get("publishedAt")),
                        raw=item,
                    )
                    results.append(comment)

                    # Fetch ALL replies if present
                    total_replies = snippet_wrap.get("totalReplyCount", 0)
                    if total_replies > 0:
                        remaining_budget = limit - len(results)
                        if remaining_budget > 0:
                            replies = await self._fetch_all_replies(comment_id, max_replies=remaining_budget)
                            results.extend(replies)

                # Use collected-result count (comments + replies) so the loop
                # terminates as soon as we actually have `limit` items. Previously
                # `remaining -= len(items)` only counted top-level comments and
                # caused extra API pages to be fetched after the budget was spent.
                remaining = limit - len(results)
                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            return results[:limit]
        except QuotaExhaustedError:
            logger.warning("YouTube API Quota exhausted! Falling back to Playwright for comments.")
            from youtube_crawler.playwright_crawler import PlaywrightYouTubeCrawler

            crawler = PlaywrightYouTubeCrawler()
            return await crawler.get_comments(post_id, limit)

    async def _fetch_all_replies(self, parent_id: str, max_replies: int = 500) -> list[CommentResult]:
        """Internal helper to fetch all replies for a comment thread via pagination.

        On error mid-pagination, flags the returned replies with ``partial=True``
        in ``capture_meta`` so callers can tell "got all 50 replies" apart from
        "fetched 10, rest lost to a network error".
        """
        replies: list[CommentResult] = []
        page_token = None
        partial = False
        partial_reason: str | None = None

        while len(replies) < max_replies:
            try:
                response = await self.api.get_comment_replies(
                    parent_id=parent_id, page_token=page_token
                )

                items = response.get("items", [])
                if not items:
                    break

                for item in items:
                    snippet = item.get("snippet") or {}
                    reply_id = item.get("id")
                    if not reply_id or not snippet:
                        logger.debug(f"Skipping malformed reply item under {parent_id}")
                        continue
                    reply = CommentResult(
                        platform="youtube",
                        source_id=reply_id,
                        content=snippet.get("textDisplay"),
                        author_name=snippet.get("authorDisplayName"),
                        author_username=self._channel_handle_from_url(snippet.get("authorChannelUrl", "")),
                        author_id=snippet.get("authorChannelId", {}).get("value"),
                        like_count=snippet.get("likeCount", 0),
                        reply_count=0,
                        parent_comment_id=parent_id,
                        published_at=self._parse_datetime(snippet.get("publishedAt")),
                        raw=item,
                    )
                    replies.append(reply)

                    if len(replies) >= max_replies:
                        break

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            except QuotaExhaustedError:
                raise
            except Exception as e:
                logger.error(
                    f"Reply fetch aborted for {parent_id} after {len(replies)} of "
                    f"(expected up to {max_replies}) replies: {e}"
                )
                partial = True
                partial_reason = str(e)
                break

        if partial and replies:
            replies[0].capture_meta["partial"] = True
            replies[0].capture_meta["partial_reason"] = partial_reason

        return replies

    # ---- Private helpers ----

    def _parse_video(self, video_id: str, snippet: dict, detail: dict) -> CrawlResult:
        """Parse YouTube API response into a CrawlResult."""
        statistics = detail.get("statistics", {})
        content_details = detail.get("contentDetails", {})
        duration_iso = content_details.get("duration")
        duration_seconds = self._iso8601_duration_to_seconds(duration_iso)

        return CrawlResult(
            platform="youtube",
            source_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=snippet.get("title"),
            content=snippet.get("description"),
            content_type="video",
            author_id=snippet.get("channelId"),
            author_name=snippet.get("channelTitle"),
            author_username=None,
            author_url=f"https://www.youtube.com/channel/{snippet.get('channelId', '')}",
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0)),
            view_count=int(statistics.get("viewCount", 0)),
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url"),
            media=[
                {
                    "type": "video",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": duration_seconds,
                    "duration_iso": duration_iso,
                    "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                    "definition": content_details.get("definition"),
                    "caption": content_details.get("caption") == "true",
                }
            ],
            tags=snippet.get("tags", []),
            published_at=self._parse_datetime(snippet.get("publishedAt")),
            raw=detail if detail else {"snippet": snippet},
        )

    async def _get_detail_via_ytdlp(self, url: str) -> CrawlResult:
        """Fallback: get video details using yt-dlp with enhanced metadata."""
        info = await self.ytdlp.extract_info(url)

        # Extract chapters if available
        chapters = []
        for chapter in info.get("chapters", []):
            chapters.append(
                {
                    "start_time": chapter.get("start_time"),
                    "end_time": chapter.get("end_time"),
                    "title": chapter.get("title"),
                }
            )

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
                    "chapters": chapters,
                    "categories": info.get("categories", []),
                    "subtitles": list(info.get("subtitles", {}).keys())
                    + list(info.get("automatic_captions", {}).keys()),
                }
            ],
            tags=info.get("tags", []),
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
    def _parse_datetime(dt_str: str | None) -> datetime | None:
        """Parse various datetime formats from YouTube. Always returns timezone-aware (UTC)."""
        if not dt_str:
            return None
        try:
            # ISO 8601 format from API
            if "T" in dt_str:
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            # YYYYMMDD format from yt-dlp
            if len(dt_str) == 8 and dt_str.isdigit():
                return datetime.strptime(dt_str, "%Y%m%d").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _iso8601_duration_to_seconds(pt: str | None) -> int | None:
        """Parse ISO 8601 duration (e.g. 'PT4M13S', 'PT1H2M3S') to integer seconds."""
        if not pt:
            return None
        match = re.match(
            r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$",
            pt,
        )
        if not match:
            return None
        days, hours, minutes, seconds = match.groups()
        total = 0
        if days:
            total += int(days) * 86400
        if hours:
            total += int(hours) * 3600
        if minutes:
            total += int(minutes) * 60
        if seconds:
            total += int(float(seconds))
        return total

    async def close(self) -> None:
        """Cleanup resources."""
        await self.api.close()
        await self.ytdlp.close()
        if self._visible_crawler:
            await self._visible_crawler.close()

    @staticmethod
    def _channel_handle_from_url(url: str) -> str | None:
        """Extract a readable handle from a YouTube channel URL.

        Returns the handle (e.g., @handle) or None if it's a standard channel ID.
        """
        if not url:
            return None
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            return None
        last = parts[-1]
        # Only return if it's a handle (starts with @)
        if last.startswith("@"):
            return last
        return None
