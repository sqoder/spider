"""
yt-dlp based YouTube Crawler.
Used as a stable fallback when no API key is provided.
"""

import asyncio
from datetime import datetime

from loguru import logger

from youtube_crawler.base import BaseCrawler, CommentResult, CrawlResult
from youtube_crawler.ytdlp_client import YtdlpClient


def _parse_upload_date(dt_str: str | None) -> datetime | None:
    """Parse YYYYMMDD strings returned by yt-dlp into datetime objects."""
    if not dt_str:
        return None
    try:
        if len(dt_str) == 8 and dt_str.isdigit():
            return datetime.strptime(dt_str, "%Y%m%d")
    except (ValueError, TypeError):
        pass
    return None


# YouTube caps a single ytsearchN query at ~300-500 unique results regardless
# of N. Above this threshold we fan out into keyword variants and dedup.
_SINGLE_SEARCH_CAP = 400

# Suffixes appended to the user's keyword. Chosen to be topic-neutral (they
# work for any query, not only tutorials) and to bias YouTube's ranker toward
# a different slice of the index each time.
_QUERY_SUFFIXES = [
    "",          # original keyword
    "tutorial",
    "guide",
    "explained",
    "review",
    "2024",
    "2023",
    "for beginners",
    "advanced",
    "full course",
]


class YtdlpYouTubeCrawler(BaseCrawler):
    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.ytdlp = YtdlpClient()
        self._visible_crawler = None

    def _get_visible_crawler(self):
        if self._visible_crawler is None:
            from youtube_crawler.visible_crawler import VisibleYouTubeCrawler

            self._visible_crawler = VisibleYouTubeCrawler()
        return self._visible_crawler

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        await self._rate_limit()
        logger.info(f"[yt-dlp] Searching YouTube for: {keyword!r} limit={limit}")

        # Fast path: at or below the single-query ceiling, one call is enough.
        if limit <= _SINGLE_SEARCH_CAP:
            return await self._single_search(keyword, limit)

        # High-volume path: expand into keyword variants, run each at the cap,
        # then dedup. The ranker returns a different slice per variant, so
        # union'd unique count grows roughly linearly until variants run out
        # of fresh IDs.
        return await self._multi_variant_search(keyword, limit)

    async def _single_search(self, keyword: str, limit: int) -> list[CrawlResult]:
        """One ytsearchN call, returned parsed. No dedup — yt-dlp itself rarely
        duplicates within a single query."""
        search_query = f"ytsearch{limit}:{keyword}"
        items = await self.ytdlp.extract_multiple_info(search_query)
        return [self._parse_info(info) for info in items if info.get("id")]

    async def _multi_variant_search(self, keyword: str, limit: int) -> list[CrawlResult]:
        """Fan out across _QUERY_SUFFIXES, dedup by video id.

        We cap each variant at _SINGLE_SEARCH_CAP (the empirical yt-dlp ceiling)
        and stop as soon as we've collected `limit` unique videos. Variants run
        sequentially: yt-dlp subprocesses are already CPU-heavy and rate
        limiter is shared, so parallel fan-out would just trip YouTube's
        per-IP throttle.
        """
        seen_ids: set[str] = set()
        results: list[CrawlResult] = []

        queries = [keyword.strip()] + [
            f"{keyword.strip()} {suffix}".strip()
            for suffix in _QUERY_SUFFIXES
            if suffix
        ]
        # Dedup queries in case the original already contains a suffix word.
        seen_q: set[str] = set()
        unique_queries = []
        for q in queries:
            low = q.lower()
            if low not in seen_q:
                unique_queries.append(q)
                seen_q.add(low)

        for q in unique_queries:
            if len(results) >= limit:
                break

            remaining = limit - len(results)
            # Ask yt-dlp for up to _SINGLE_SEARCH_CAP per variant. Asking for
            # `remaining` only would waste variant diversity (YouTube caps early
            # and we'd redo the same small head over and over).
            per_variant_target = min(_SINGLE_SEARCH_CAP, max(remaining, 50))

            logger.info(
                f"[yt-dlp] Variant {q!r}: requesting {per_variant_target} "
                f"(collected {len(results)}/{limit} unique so far)"
            )
            try:
                batch = await self._single_search(q, per_variant_target)
            except Exception as e:
                logger.warning(f"[yt-dlp] Variant {q!r} failed: {e}")
                continue

            added = 0
            for item in batch:
                vid = item.source_id
                if not vid or vid in seen_ids:
                    continue
                seen_ids.add(vid)
                results.append(item)
                added += 1
                if len(results) >= limit:
                    break

            logger.info(
                f"[yt-dlp] Variant {q!r}: got {len(batch)}, added {added} new"
            )

            # Brief pause between variants — shared rate limiter handles the
            # per-request delay, but a cross-variant cushion helps avoid
            # tripping the search-endpoint throttle.
            await asyncio.sleep(1.0)

        logger.info(
            f"[yt-dlp] Multi-variant search for {keyword!r} done: "
            f"{len(results)} unique across {len(unique_queries)} variants"
        )
        return results[:limit]

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
        url = (
            info.get("original_url")
            or info.get("webpage_url")
            or f"https://www.youtube.com/watch?v={info.get('id')}"
        )

        # Extract chapters
        chapters = []
        for chapter in info.get("chapters") or []:
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
            author_avatar=info.get("avatar")
            or info.get("channel_thumbnail")
            or info.get("channel_avatar"),
            tags=info.get("tags", []),
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
            published_at=_parse_upload_date(info.get("upload_date")),
            raw=info,
        )

    async def close(self) -> None:
        await self.ytdlp.close()
        if self._visible_crawler:
            await self._visible_crawler.close()
