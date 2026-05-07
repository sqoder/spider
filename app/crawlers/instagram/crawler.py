"""
Instagram crawler implementation (Phase 2).
Uses native web endpoints for public profiles and single posts to bypass login.
"""

import asyncio
import json
import re
from datetime import UTC, datetime

from loguru import logger
from scrapling import Fetcher

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult


class InstagramCrawler(BaseCrawler):
    """Instagram platform crawler using Scrapling Fetcher."""

    platform = "instagram"

    def __init__(self):
        super().__init__()
        self._fetcher = Fetcher(
            timeout=30000,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
        )
        logger.info("Instagram crawler initialized with Scrapling Fetcher")

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """
        Search Instagram by hashtag.
        Note: Instagram search is heavily protected and requires login.
        """
        await self._rate_limit()
        logger.warning("Instagram hashtag search is restricted and requires login. Skipping.")
        return []

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get posts from an Instagram user's public profile using Scrapling Fetcher with Proxy and Account Pool."""
        await self._rate_limit()
        username = username.lstrip("@")
        logger.info(f"Instagram user posts: '{username}', limit={limit}")

        from app.core.account_manager import account_manager
        from app.core.proxy_manager import proxy_manager

        proxy = proxy_manager.get_proxy()
        fetcher = Fetcher(
            timeout=30000,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            proxy=proxy,
        )

        url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
        headers = {
            "X-IG-App-ID": "936619743392459",
            "Referer": f"https://www.instagram.com/{username}/",
        }

        account_cookie = await account_manager.get_healthy_cookie_for_platform("instagram")
        if account_cookie and account_cookie.get("cookies_data"):
            cookies_dict = account_cookie.get("cookies_data")
            if isinstance(cookies_dict, dict):
                cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
                headers["Cookie"] = cookie_str
            elif isinstance(cookies_dict, list):
                # Netscape or list of dicts format
                cookie_str = "; ".join([f"{c.get('name')}={c.get('value')}" for c in cookies_dict if isinstance(c, dict)])
                headers["Cookie"] = cookie_str

        try:

            def _do_fetch():
                return fetcher.get(url, headers=headers)

            response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

            if response.status != 200:
                logger.warning(f"Instagram API failed with status {response.status}")
                if account_cookie:
                    if response.status == 429:
                        await account_manager.report_account_rate_limited(account_cookie["account_id"])
                    elif response.status in (401, 403):
                        await account_manager.report_account_failed(account_cookie["account_id"])
                return []

            data = response.json()
            user_data = data.get("data", {}).get("user", {})
            if not user_data:
                logger.warning(f"No user data found for {username}")
                return []

            edges = user_data.get("edge_owner_to_timeline_media", {}).get("edges", [])
            results = []
            for edge in edges:
                node = edge.get("node", {})
                if node:
                    # Inject owner info so _parse_instagram_item can read it
                    node["owner"] = {
                        "id": user_data.get("id"),
                        "username": user_data.get("username"),
                        "full_name": user_data.get("full_name"),
                    }
                    parsed = self._parse_instagram_item(node)
                    if parsed:
                        results.append(parsed)
                if len(results) >= limit:
                    break

            return results

        except Exception as e:
            logger.error(f"Instagram user posts failed for {username}: {e}")
            return []

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Get detailed info for a single Instagram post using Scrapling Fetcher."""
        await self._rate_limit()
        logger.info(f"Instagram post detail: {url}")

        # Extract shortcode
        shortcode_match = re.search(r"/(?:p|reels|reel)/([A-Za-z0-9_-]+)", url)
        if not shortcode_match:
            raise ValueError(f"Could not extract shortcode from url: {url}")
        shortcode = shortcode_match.group(1)

        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"

        try:

            def _do_fetch():
                return self._fetcher.get(embed_url)

            response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)
            html_data = response.html_content

            idx = html_data.find("gql_data")
            if idx == -1:
                idx = html_data.find("shortcode_media")

            if idx != -1:
                sub = html_data[idx:]
                start_brace = sub.find("{")
                if start_brace != -1:
                    raw_to_clean = sub[start_brace:]
                    raw_clean = raw_to_clean.replace('\\"', '"').replace("\\/", "/")
                    try:
                        data, decode_idx = json.JSONDecoder().raw_decode(raw_clean)
                        media_data = data.get("shortcode_media", {})
                        if media_data:
                            parsed = self._parse_instagram_item(media_data)
                            if parsed:
                                return parsed
                    except Exception as json_err:
                        logger.debug(f"JSON raw_decode failed: {json_err}")

            raise ValueError("Could not find shortcode_media in embed page")

        except Exception as e:
            logger.error(f"Instagram post detail failed: {e}")
            raise

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Instagram comments are not supported in Phase 2."""
        logger.warning("Instagram comments are not supported yet")
        return []

    # ---- Private helpers ----

    def _parse_instagram_item(self, data: dict) -> CrawlResult | None:
        """Parse Instagram metadata into a CrawlResult."""
        if not data:
            return None

        post_id = str(data.get("shortcode", data.get("id", "")))
        if not post_id:
            return None

        # Determine content type
        typename = data.get("__typename", data.get("typename", data.get("media_type", "")))
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
                    published_at = datetime.fromtimestamp(timestamp, tz=UTC)
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
            title=None,
            content=caption,
            content_type=content_type,
            author_id=str(owner.get("id", "")),
            author_name=owner.get("full_name", ""),
            author_username=username,
            author_url=f"https://www.instagram.com/{username}/" if username else None,
            like_count=data.get("edge_media_preview_like", {}).get(
                "count", data.get("like_count", data.get("edge_liked_by", {}).get("count", 0))
            )
            or 0,
            comment_count=data.get("edge_media_to_comment", {}).get(
                "count", data.get("comment_count", 0)
            )
            or 0,
            view_count=data.get("video_view_count", 0) or 0,
            media=media,
            thumbnail_url=data.get("thumbnail_src", data.get("display_url")),
            published_at=published_at,
            raw=data,
        )

    async def close(self) -> None:
        pass
