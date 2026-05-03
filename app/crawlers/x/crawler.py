"""
X/Twitter crawler implementation (Phase 3).
Uses twscrape for limited public content scraping.
Scope: single URL parsing, public profile info, limited keyword search.
"""

from datetime import datetime
from typing import Optional

from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult


class XCrawler(BaseCrawler):
    """X/Twitter platform crawler (Phase 3 - limited capabilities)."""

    platform = "x"

    def __init__(self):
        super().__init__()
        self._twscrape_pool = None
        logger.info("X/Twitter crawler initialized (limited mode)")

    async def _get_pool(self):
        """Lazy-initialize twscrape account pool."""
        if self._twscrape_pool is None:
            try:
                from twscrape import AccountsPool, API
                self._twscrape_pool = AccountsPool()
                self._api = API(self._twscrape_pool)
                logger.info("twscrape pool initialized")
            except ImportError:
                logger.error("twscrape is not installed. Install with: pip install twscrape")
                raise

        return self._api

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search X/Twitter by keyword.
        Note: Requires valid twscrape accounts configured.
        """
        await self._rate_limit()
        logger.info(f"X search: '{keyword}', limit={limit}")

        try:
            api = await self._get_pool()
            results = []

            async for tweet in api.search(keyword, limit=limit):
                result = self._parse_tweet(tweet)
                results.append(result)
                if len(results) >= limit:
                    break

            return results

        except Exception as e:
            logger.error(f"X search failed: {e}")
            return []

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get tweets from a user's profile."""
        await self._rate_limit()
        logger.info(f"X user posts: '{username}', limit={limit}")

        try:
            api = await self._get_pool()
            results = []

            # First get user info
            user = await api.user_by_login(username)
            if not user:
                logger.warning(f"X user not found: {username}")
                return []

            async for tweet in api.user_tweets(user.id, limit=limit):
                result = self._parse_tweet(tweet)
                results.append(result)
                if len(results) >= limit:
                    break

            return results

        except Exception as e:
            logger.error(f"X user posts failed: {e}")
            return []

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detail for a single tweet by URL."""
        await self._rate_limit()
        logger.info(f"X post detail: {url}")

        try:
            api = await self._get_pool()
            tweet_id = self._extract_tweet_id(url)
            tweet = await api.tweet_by_id(int(tweet_id))

            if tweet:
                return self._parse_tweet(tweet)

            raise ValueError(f"Tweet not found: {url}")

        except Exception as e:
            logger.error(f"X post detail failed: {e}")
            raise

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """
        Get replies to a tweet.
        Note: Reply fetching via twscrape is limited.
        """
        logger.warning("X/Twitter comments support is limited in Phase 3")
        return []

    # ---- Private helpers ----

    def _parse_tweet(self, tweet) -> CrawlResult:
        """Parse a twscrape Tweet object into a CrawlResult."""
        # Build media list
        media = []
        if hasattr(tweet, "media") and tweet.media:
            if hasattr(tweet.media, "photos"):
                for photo in tweet.media.photos:
                    media.append({"type": "image", "url": photo.url})
            if hasattr(tweet.media, "videos"):
                for video in tweet.media.videos:
                    # Get highest quality variant
                    variants = getattr(video, "variants", [])
                    best_url = ""
                    for v in variants:
                        if hasattr(v, "url"):
                            best_url = v.url
                    media.append({
                        "type": "video",
                        "url": best_url,
                        "duration": getattr(video, "duration", None),
                    })

        user = tweet.user if hasattr(tweet, "user") else None

        return CrawlResult(
            platform="x",
            source_id=str(tweet.id),
            url=f"https://x.com/{user.username}/status/{tweet.id}" if user else None,
            title=None,  # Tweets don't have titles
            content=tweet.rawContent if hasattr(tweet, "rawContent") else str(tweet),
            content_type="tweet",
            author_id=str(user.id) if user else None,
            author_name=user.displayname if user else None,
            author_username=user.username if user else None,
            author_url=f"https://x.com/{user.username}" if user else None,
            author_avatar=user.profileImageUrl if user and hasattr(user, "profileImageUrl") else None,
            like_count=getattr(tweet, "likeCount", 0) or 0,
            comment_count=getattr(tweet, "replyCount", 0) or 0,
            share_count=getattr(tweet, "retweetCount", 0) or 0,
            view_count=getattr(tweet, "viewCount", 0) or 0,
            media=media,
            published_at=tweet.date if hasattr(tweet, "date") else None,
            raw=tweet.dict() if hasattr(tweet, "dict") else {},
        )

    @staticmethod
    def _extract_tweet_id(url: str) -> str:
        """Extract tweet ID from URL."""
        import re
        match = re.search(r"/status/(\d+)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Cannot extract tweet ID from: {url}")

    async def close(self) -> None:
        pass
