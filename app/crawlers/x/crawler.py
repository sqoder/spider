"""
X/Twitter crawler implementation (Phase 3).
Uses twscrape for limited public content scraping.
Scope: single URL parsing, public profile info, limited keyword search.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional

from scrapling import Fetcher
from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult


class XCrawler(BaseCrawler):
    """X/Twitter platform crawler (Phase 3) using Scrapling Fetcher."""

    platform = "x"

    def __init__(self):
        super().__init__()
        self._twscrape_pool = None
        self._fetcher = Fetcher(
            timeout=30000,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
        )
        logger.info("X/Twitter crawler initialized (Login-free Syndication mode with Scrapling)")

    async def _get_pool(self):
        """Lazy-initialize twscrape account pool for search."""
        if self._twscrape_pool is None:
            try:
                from twscrape import API, AccountsPool

                self._twscrape_pool = AccountsPool()
                self._api = API(self._twscrape_pool)
            except ImportError:
                pass
        return getattr(self, "_api", None)

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search X/Twitter by keyword.
        Requires valid twscrape accounts configured because Twitter completely blocks anonymous search.
        """
        await self._rate_limit()
        logger.info(f"X search: '{keyword}', limit={limit}")

        api = await self._get_pool()
        if not api:
            logger.warning(
                "twscrape not installed or accounts not configured. X keyword search requires accounts."
            )
            logger.warning("Please run `twscrape add_accounts` or use 'user' mode in config.")
            return []

        try:
            results = []
            async for tweet in api.search(keyword, limit=limit):
                result = self._parse_twscrape_tweet(tweet)
                results.append(result)
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.error(f"X search failed: {e}")
            logger.warning(
                "If this is an account error, please use 'user' mode which is login-free."
            )
            return []

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get tweets from a user's profile using the login-free Syndication API via Scrapling Fetcher."""
        await self._rate_limit()
        username = username.lstrip("@")
        logger.info(f"X user posts: '{username}', limit={limit}")

        url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:

            def _do_fetch():
                return self._fetcher.get(url, headers=headers)

            response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

            if response.status_code != 200:
                logger.warning(f"X syndication API failed with status {response.status_code}")
                return []

            # Parse the NEXT_DATA JSON blob
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', response.text
            )
            if not match:
                logger.warning(f"Could not find timeline data for user {username}")
                return []

            data = json.loads(match.group(1))
            instructions = (
                data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
            )

            results = []
            for entry in instructions:
                content = entry.get("content", {}).get("tweet", {})
                if content:
                    parsed = self._parse_syndication_tweet(content, username)
                    if parsed:
                        results.append(parsed)
                if len(results) >= limit:
                    break

            return results

        except Exception as e:
            logger.error(f"X user posts failed: {e}")
            return []

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detail for a single tweet by URL using yt-dlp."""
        await self._rate_limit()
        logger.info(f"X post detail: {url}")

        import asyncio

        cmd = ["yt-dlp", "--dump-json", "--no-download", url]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            if process.returncode != 0:
                raise ValueError(f"yt-dlp failed for {url}")

            info = json.loads(stdout.decode("utf-8"))

            published_at = None
            ts = info.get("timestamp")
            if ts:
                try:
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                except:
                    pass

            return CrawlResult(
                platform="x",
                source_id=info.get("id", ""),
                url=url,
                title=info.get("title", ""),
                content=info.get("description", ""),
                content_type="tweet",
                author_id=info.get("uploader_id", ""),
                author_name=info.get("uploader", ""),
                author_username=info.get("uploader_id", ""),
                author_url=info.get("uploader_url"),
                like_count=info.get("like_count", 0),
                comment_count=info.get("comment_count", 0),
                share_count=info.get("repost_count", 0),
                view_count=info.get("view_count", 0),
                media=[{"type": "video", "url": url}] if info.get("duration") else [],
                thumbnail_url=info.get("thumbnail"),
                published_at=published_at,
                raw=info,
            )
        except Exception as e:
            logger.error(f"X post detail failed: {e}")
            raise

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Get replies to a tweet."""
        logger.warning("X/Twitter comments support requires login. Skipping.")
        return []

    # ---- Private helpers ----

    def _parse_syndication_tweet(self, tweet: dict, username: str) -> Optional[CrawlResult]:
        if not tweet.get("id_str"):
            return None

        tid = tweet.get("id_str")
        text = tweet.get("text", "") or tweet.get("full_text", "")

        user = tweet.get("user", {})
        author_username = user.get("screen_name", username)

        media = []
        extended = tweet.get("extended_entities", {}) or tweet.get("entities", {})
        if extended.get("media"):
            for m in extended["media"]:
                m_type = m.get("type", "image")
                media_info = {"type": m_type, "url": m.get("media_url_https", "")}
                if m_type == "video" and m.get("video_info"):
                    variants = m["video_info"].get("variants", [])
                    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4s:
                        mp4s.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
                        media_info["url"] = mp4s[0]["url"]
                media.append(media_info)

        published_at = None
        created_at = tweet.get("created_at")
        if created_at:
            try:
                # "Mon Jul 29 20:33:27 +0000 2024"
                dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                published_at = dt
            except:
                pass

        return CrawlResult(
            platform="x",
            source_id=tid,
            url=f"https://x.com/{author_username}/status/{tid}",
            title=None,
            content=text,
            content_type="tweet",
            author_id=user.get("id_str", ""),
            author_name=user.get("name", ""),
            author_username=author_username,
            author_url=f"https://x.com/{author_username}",
            author_avatar=user.get("profile_image_url_https", ""),
            like_count=tweet.get("favorite_count", 0),
            comment_count=tweet.get("reply_count", 0),
            share_count=tweet.get("retweet_count", 0),
            view_count=0,
            media=media,
            published_at=published_at,
            raw=tweet,
        )

    def _parse_twscrape_tweet(self, tweet) -> CrawlResult:
        media = []
        if hasattr(tweet, "media") and tweet.media:
            if hasattr(tweet.media, "photos"):
                for photo in tweet.media.photos:
                    media.append({"type": "image", "url": photo.url})
            if hasattr(tweet.media, "videos"):
                for video in tweet.media.videos:
                    variants = getattr(video, "variants", [])
                    best_url = ""
                    for v in variants:
                        if hasattr(v, "url"):
                            best_url = v.url
                    media.append({"type": "video", "url": best_url})

        user = tweet.user if hasattr(tweet, "user") else None

        return CrawlResult(
            platform="x",
            source_id=str(tweet.id),
            url=f"https://x.com/{user.username}/status/{tweet.id}" if user else None,
            content=tweet.rawContent if hasattr(tweet, "rawContent") else str(tweet),
            content_type="tweet",
            author_id=str(user.id) if user else None,
            author_name=user.displayname if user else None,
            author_username=user.username if user else None,
            author_url=f"https://x.com/{user.username}" if user else None,
            like_count=getattr(tweet, "likeCount", 0) or 0,
            comment_count=getattr(tweet, "replyCount", 0) or 0,
            share_count=getattr(tweet, "retweetCount", 0) or 0,
            view_count=getattr(tweet, "viewCount", 0) or 0,
            media=media,
            published_at=tweet.date if hasattr(tweet, "date") else None,
            raw={},
        )

    async def close(self) -> None:
        pass
