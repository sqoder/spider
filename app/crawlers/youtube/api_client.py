"""
YouTube Data API v3 client.
Handles search, video details, channel info, and comments.
Includes quota tracking to stay within daily limits.
"""

import asyncio

from loguru import logger
from scrapling import Fetcher

from app.core.config import get_settings
from app.core.exceptions import APIKeyMissingError, CrawlError, QuotaExhaustedError
from app.core.proxy_manager import proxy_manager


class YouTubeAPIClient:
    """
    Client for YouTube Data API v3 using Scrapling Fetcher.
    Handles search, video details, channel info, and comments.
    Includes quota tracking to stay within daily limits.
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    # Quota costs per endpoint
    QUOTA_COSTS = {
        "search": 100,
        "videos": 1,
        "channels": 1,
        "commentThreads": 1,
        "comments": 1,
    }

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.youtube_api_key
        self.daily_quota = settings.youtube_daily_quota
        self._quota_used = 0

        if not self.api_key:
            raise APIKeyMissingError("youtube", "YOUTUBE_API_KEY")

        # Initialize base fetcher
        self._fetcher = Fetcher(timeout=30000, headers={"Accept": "application/json"})

    def _check_quota(self, endpoint: str) -> None:
        """Check if we have enough quota for the request."""
        cost = self.QUOTA_COSTS.get(endpoint, 1)
        if self._quota_used + cost > self.daily_quota:
            raise QuotaExhaustedError(
                "youtube",
                quota_used=self._quota_used,
                quota_limit=self.daily_quota,
            )

    async def _request(self, endpoint: str, params: dict, retry_count: int | None = None) -> dict:
        """Make an API request with quota tracking and proxy rotation using Scrapling."""
        self._check_quota(endpoint)

        if retry_count is None:
            settings = get_settings()
            retry_count = settings.max_retries

        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(retry_count + 1):
            proxy_url = None
            if proxy_manager.enabled:
                proxy_url = proxy_manager.get_proxy()

            try:

                def _do_fetch(proxy_url=proxy_url):
                    # For simplicity and thread-safety in executor, we use a local fetcher or configure proxy
                    f = self._fetcher
                    if proxy_url:
                        f = Fetcher(
                            proxy=proxy_url, timeout=30000, headers={"Accept": "application/json"}
                        )
                    return f.get(url, params=params)

                response = await asyncio.get_running_loop().run_in_executor(None, _do_fetch)

                if response.status != 200:
                    logger.warning(
                        f"YouTube API request failed (status {response.status}): {response.text[:100]}"
                    )
                    if attempt < retry_count and response.status >= 500:
                        await asyncio.sleep(2**attempt)
                        continue
                    response.raise_for_status()

                self._quota_used += self.QUOTA_COSTS.get(endpoint, 1)
                return response.json()
            except Exception as e:
                if attempt < retry_count:
                    logger.warning(
                        f"YouTube API request failed (attempt {attempt + 1}): {e}. Retrying..."
                    )
                    await asyncio.sleep(2**attempt)
                    continue
                logger.error(f"YouTube API error after {retry_count} retries: {e}")
                raise CrawlError("youtube", endpoint, str(e)) from e

        raise CrawlError("youtube", endpoint, "_request exited retry loop without result")

    async def search_videos(
        self,
        query: str,
        max_results: int = 20,
        order: str = "relevance",
        published_after: str | None = None,
        published_before: str | None = None,
        page_token: str | None = None,
    ) -> dict:
        """
        Search for videos with time range support.
        """
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": min(max_results, 50),
            "order": order,
        }
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before
        if page_token:
            params["pageToken"] = page_token

        return await self._request("search", params)

    async def get_video_details(self, video_ids: list[str]) -> dict:
        """
        Get detailed info for one or more videos.

        Args:
            video_ids: List of video IDs (max 50)

        Returns:
            API response dict with video details
        """
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids[:50]),
        }
        return await self._request("videos", params)

    async def get_channel_info(
        self, channel_id: str | None = None, username: str | None = None
    ) -> dict:
        """
        Get channel information.

        Args:
            channel_id: YouTube channel ID
            username: YouTube username/handle

        Returns:
            API response dict with channel info
        """
        params = {
            "part": "snippet,statistics,contentDetails",
        }
        if channel_id:
            params["id"] = channel_id
        elif username:
            params["forHandle"] = username

        return await self._request("channels", params)

    async def get_channel_videos(
        self,
        channel_id: str,
        max_results: int = 20,
        page_token: str | None = None,
    ) -> dict:
        """Search for videos from a specific channel."""
        params = {
            "part": "snippet",
            "type": "video",
            "channelId": channel_id,
            "maxResults": min(max_results, 50),
            "order": "date",
        }
        if page_token:
            params["pageToken"] = page_token

        return await self._request("search", params)

    async def get_comments(
        self,
        video_id: str,
        max_results: int = 50,
        order: str = "relevance",
        page_token: str | None = None,
    ) -> dict:
        """
        Get top-level comment threads for a video.

        Args:
            video_id: YouTube video ID
            max_results: Maximum comments (1-100)
            order: Sort order (relevance, time)
            page_token: Pagination token

        Returns:
            API response dict with comment threads
        """
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": min(max_results, 100),
            "order": order,
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        return await self._request("commentThreads", params)

    async def get_comment_replies(
        self,
        parent_id: str,
        max_results: int = 100,
        page_token: str | None = None,
    ) -> dict:
        """
        Get all replies for a specific comment thread.

        Args:
            parent_id: The ID of the parent comment
            max_results: Maximum replies per request (1-100)
            page_token: Pagination token

        Returns:
            API response dict with comments (replies)
        """
        params = {
            "part": "snippet",
            "parentId": parent_id,
            "maxResults": min(max_results, 100),
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        return await self._request("comments", params)

    @property
    def quota_remaining(self) -> int:
        """Get remaining daily quota."""
        return max(0, self.daily_quota - self._quota_used)

    async def close(self) -> None:
        """Close the HTTP client."""
        # Scrapling Fetcher is managed elsewhere or sync, no explicit aclose needed
        pass
