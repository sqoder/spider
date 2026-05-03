"""
Reddit crawler implementation.
Uses the official Reddit API for all operations.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.reddit.api_client import RedditAPIClient


class RedditCrawler(BaseCrawler):
    """Reddit platform crawler."""

    platform = "reddit"

    def __init__(self):
        super().__init__()
        self.api = RedditAPIClient()

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """Search Reddit posts by keyword."""
        await self._rate_limit()
        logger.info(f"Reddit search: '{keyword}', limit={limit}")

        results = []
        after = None
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, 100)
            response = await self.api.search(
                query=keyword,
                limit=batch_size,
                after=after,
            )

            data = response.get("data", {})
            children = data.get("children", [])
            if not children:
                break

            for child in children:
                post_data = child.get("data", {})
                result = self._parse_post(post_data)
                results.append(result)

            remaining -= len(children)
            after = data.get("after")
            if not after:
                break

        logger.info(f"Reddit search returned {len(results)} results")
        return results[:limit]

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get posts from a Reddit user."""
        await self._rate_limit()
        logger.info(f"Reddit user posts: '{username}', limit={limit}")

        results = []
        after = None
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, 100)
            response = await self.api.get_user_posts(
                username=username,
                limit=batch_size,
                after=after,
            )

            data = response.get("data", {})
            children = data.get("children", [])
            if not children:
                break

            for child in children:
                post_data = child.get("data", {})
                result = self._parse_post(post_data)
                results.append(result)

            remaining -= len(children)
            after = data.get("after")
            if not after:
                break

        return results[:limit]

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detailed info for a single Reddit post."""
        await self._rate_limit()

        subreddit, post_id = self._extract_post_info(url)
        logger.info(f"Reddit post detail: r/{subreddit}/{post_id}")

        response = await self.api.get_post_detail(subreddit, post_id)

        # Response is a list: [post_listing, comments_listing]
        if isinstance(response, list) and len(response) > 0:
            post_listing = response[0]
            children = post_listing.get("data", {}).get("children", [])
            if children:
                post_data = children[0].get("data", {})
                return self._parse_post(post_data)

        raise ValueError(f"Could not parse post from URL: {url}")

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Get comments for a Reddit post."""
        await self._rate_limit()
        logger.info(f"Reddit comments: {post_id}, limit={limit}")

        # Post ID might be in format "subreddit:post_id" or just "post_id"
        if ":" in post_id:
            subreddit, pid = post_id.split(":", 1)
        else:
            # Need to figure out the subreddit — use post_id as subreddit=all fallback
            subreddit = "all"
            pid = post_id

        response = await self.api.get_comments(subreddit, pid, limit=limit)

        results = []
        if isinstance(response, list) and len(response) > 1:
            comments_listing = response[1]
            children = comments_listing.get("data", {}).get("children", [])
            self._parse_comments_recursive(children, results, limit)

        return results[:limit]

    # ---- Private helpers ----

    def _parse_post(self, data: dict) -> CrawlResult:
        """Parse Reddit post data into a CrawlResult."""
        # Determine content type
        content_type = "text"
        media = []

        if data.get("is_video"):
            content_type = "video"
            video_url = (
                data.get("media", {}).get("reddit_video", {}).get("fallback_url")
            )
            if video_url:
                media.append(
                    {
                        "type": "video",
                        "url": video_url,
                        "duration": data.get("media", {})
                        .get("reddit_video", {})
                        .get("duration"),
                    }
                )
        elif data.get("post_hint") == "image":
            content_type = "image"
            if data.get("url"):
                media.append({"type": "image", "url": data["url"]})
        elif data.get("is_gallery"):
            content_type = "gallery"
            # Extract gallery items
            gallery_data = data.get("gallery_data", {}).get("items", [])
            media_metadata = data.get("media_metadata", {})
            for item in gallery_data:
                media_id = item.get("media_id")
                if media_id and media_id in media_metadata:
                    meta = media_metadata[media_id]
                    source = meta.get("s", {})
                    media.append(
                        {
                            "type": "image",
                            "url": source.get("u", "").replace("&amp;", "&"),
                        }
                    )

        permalink = data.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else None

        return CrawlResult(
            platform="reddit",
            source_id=data.get("id", ""),
            url=url,
            title=data.get("title"),
            content=data.get("selftext", ""),
            content_type=content_type,
            author_id=data.get("author_fullname"),
            author_name=data.get("author"),
            author_username=data.get("author"),
            author_url=f"https://www.reddit.com/user/{data.get('author', '')}",
            like_count=data.get("ups", 0),
            comment_count=data.get("num_comments", 0),
            share_count=data.get("num_crossposts", 0),
            view_count=0,
            media=media,
            thumbnail_url=(
                data.get("thumbnail")
                if data.get("thumbnail", "").startswith("http")
                else None
            ),
            published_at=(
                datetime.fromtimestamp(data.get("created_utc", 0), tz=timezone.utc)
                if data.get("created_utc")
                else None
            ),
            raw=data,
        )

    def _parse_comments_recursive(
        self,
        children: list[dict],
        results: list[CommentResult],
        limit: int,
    ) -> None:
        """Recursively parse comment tree."""
        for child in children:
            if len(results) >= limit:
                break

            if child.get("kind") != "t1":
                continue

            data = child.get("data", {})
            comment = CommentResult(
                platform="reddit",
                source_id=data.get("id", ""),
                content=data.get("body", ""),
                author_name=data.get("author"),
                author_username=data.get("author"),
                author_id=data.get("author_fullname"),
                like_count=data.get("ups", 0),
                reply_count=0,
                parent_comment_id=data.get("parent_id"),
                published_at=(
                    datetime.fromtimestamp(data.get("created_utc", 0), tz=timezone.utc)
                    if data.get("created_utc")
                    else None
                ),
                raw=data,
            )
            results.append(comment)

            # Parse replies
            replies = data.get("replies")
            if isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                self._parse_comments_recursive(reply_children, results, limit)

    @staticmethod
    def _extract_post_info(url: str) -> tuple[str, str]:
        """Extract subreddit and post ID from Reddit URL."""
        pattern = r"reddit\.com/r/(\w+)/comments/(\w+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
        raise ValueError(f"Cannot parse Reddit URL: {url}")

    async def close(self) -> None:
        await self.api.close()
