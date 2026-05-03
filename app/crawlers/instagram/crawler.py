"""
Instagram crawler implementation (Phase 2).
Uses gallery-dl for public profile, posts, and reels.
First phase scope: public profiles, public posts, public reels, single URL parsing.
"""

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.tiktok.gallerydl_client import GalleryDLClient


class InstagramCrawler(BaseCrawler):
    """Instagram platform crawler (Phase 2)."""

    platform = "instagram"

    def __init__(self):
        super().__init__()
        self.gallery_dl = GalleryDLClient(platform="instagram")

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search Instagram by hashtag.
        Note: Instagram search is very limited without login.
        """
        await self._rate_limit()
        logger.info(f"Instagram search: '{keyword}', limit={limit}")

        tag = keyword.replace(" ", "").replace("#", "")
        url = f"https://www.instagram.com/explore/tags/{tag}/"

        try:
            items = await self.gallery_dl.extract_metadata(url)
            results = []
            for item in items[:limit]:
                result = self._parse_instagram_item(item)
                if result:
                    results.append(result)
            return results
        except Exception as e:
            logger.warning(f"Instagram search failed: {e}")
            return []

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get posts from an Instagram user's public profile."""
        await self._rate_limit()
        logger.info(f"Instagram user posts: '{username}', limit={limit}")

        items = await self.gallery_dl.get_user_content(username, limit=limit)

        results = []
        for item in items:
            result = self._parse_instagram_item(item)
            if result:
                results.append(result)

        return results[:limit]

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detailed info for a single Instagram post."""
        await self._rate_limit()
        logger.info(f"Instagram post detail: {url}")

        items = await self.gallery_dl.extract_metadata(url)
        if items:
            result = self._parse_instagram_item(items[0])
            if result:
                return result

        raise ValueError(f"Could not parse Instagram post from: {url}")

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Instagram comments are not supported in Phase 2."""
        logger.warning("Instagram comments are not supported yet")
        return []

    # ---- Private helpers ----

    def _parse_instagram_item(self, data: dict) -> Optional[CrawlResult]:
        """Parse gallery-dl Instagram metadata into a CrawlResult."""
        if not data:
            return None

        post_id = str(data.get("shortcode", data.get("id", "")))
        if not post_id:
            return None

        # Determine content type
        typename = data.get("typename", data.get("media_type", ""))
        if "video" in str(typename).lower() or "reel" in str(typename).lower():
            content_type = "video"
        elif "carousel" in str(typename).lower() or "sidecar" in str(typename).lower():
            content_type = "carousel"
        else:
            content_type = "image"

        # Build media
        media = []
        display_url = data.get("display_url", data.get("url"))
        video_url = data.get("video_url")
        if video_url:
            media.append({"type": "video", "url": video_url})
        elif display_url:
            media.append({"type": "image", "url": display_url})

        # Author info
        owner = data.get("owner", data.get("user", {}))
        if isinstance(owner, str):
            owner = {"username": owner}

        username = owner.get("username", data.get("username", ""))

        # Timestamps
        published_at = None
        timestamp = data.get("taken_at_timestamp", data.get("date"))
        if timestamp:
            try:
                if isinstance(timestamp, (int, float)):
                    published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Caption
        caption = data.get("description", "")
        if not caption:
            edge_caption = data.get("edge_media_to_caption", {})
            edges = edge_caption.get("edges", [])
            if edges:
                caption = edges[0].get("node", {}).get("text", "")

        return CrawlResult(
            platform="instagram",
            source_id=post_id,
            url=f"https://www.instagram.com/p/{post_id}/" if post_id else None,
            title=None,  # Instagram posts don't have titles
            content=caption,
            content_type=content_type,
            author_id=str(owner.get("id", "")),
            author_name=owner.get("full_name", ""),
            author_username=username,
            author_url=f"https://www.instagram.com/{username}/" if username else None,
            like_count=data.get("edge_media_preview_like", {}).get("count", data.get("like_count", 0)) or 0,
            comment_count=data.get("edge_media_to_comment", {}).get("count", data.get("comment_count", 0)) or 0,
            view_count=data.get("video_view_count", 0) or 0,
            media=media,
            thumbnail_url=data.get("thumbnail_src", data.get("display_url")),
            published_at=published_at,
            raw=data,
        )

    async def close(self) -> None:
        pass
