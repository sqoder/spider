"""
YouTube Data API v3 client.
Handles search, video details, channel info, and comments.
Includes quota tracking to stay within daily limits.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import (APIKeyMissingError, CrawlError,
                                 QuotaExhaustedError)
from app.core.proxy_manager import proxy_manager


class YouTubeAPIClient:
    """
    Client for YouTube Data API v3.

    Quota costs (approximate):
        - search.list: 100 units
        - videos.list: 1 unit
        - channels.list: 1 unit
        - commentThreads.list: 1 unit
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

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    def _check_quota(self, endpoint: str) -> None:
        """Check if we have enough quota for the request."""
        cost = self.QUOTA_COSTS.get(endpoint, 1)
        if self._quota_used + cost > self.daily_quota:
            raise QuotaExhaustedError(
                "youtube",
                quota_used=self._quota_used,
                quota_limit=self.daily_quota,
            )

    async def _request(self, endpoint: str, params: dict, retry_count: int = 2) -> dict:
        """Make an API request with quota tracking and proxy rotation."""
        self._check_quota(endpoint)

        params["key"] = self.api_key
        url = f"/{endpoint}"

        for attempt in range(retry_count + 1):
            proxies = None
            if proxy_manager.enabled:
                proxy_url = proxy_manager.get_proxy()
                if proxy_url:
                    proxies = {"http://": proxy_url, "https://": proxy_url}

            try:
                if proxies:
                    async with httpx.AsyncClient(proxies=proxies, timeout=30.0) as client:
                        response = await client.get(self.BASE_URL + url, params=params)
                else:
                    response = await self._client.get(url, params=params)
                
                response.raise_for_status()
                self._quota_used += self.QUOTA_COSTS.get(endpoint, 1)
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt < retry_count:
                    logger.warning(f"YouTube API request failed (attempt {attempt+1}): {e}. Retrying...")
                    continue
                logger.error(f"YouTube API error after {retry_count} retries: {e}")
                raise CrawlError("youtube", endpoint, str(e))

        # Should never reach here, but guard against implicit None return
        raise CrawlError("youtube", endpoint, "_request exited retry loop without result")

    async def search_videos(
        self,
        query: str,
        max_results: int = 20,
        order: str = "relevance",
        published_after: Optional[str] = None,
        page_token: Optional[str] = None,
    ) -> dict:
        """
        Search for videos.

        Args:
            query: Search query string
            max_results: Maximum results (1-50)
            order: Sort order (relevance, date, viewCount, rating)
            published_after: ISO 8601 datetime string
            page_token: Pagination token

        Returns:
            API response dict with items and pagination info
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
        self, channel_id: Optional[str] = None, username: Optional[str] = None
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
        page_token: Optional[str] = None,
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
        page_token: Optional[str] = None,
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
        page_token: Optional[str] = None,
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
        await self._client.aclose()
