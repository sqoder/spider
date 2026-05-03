"""
Reddit OAuth API client.
Handles authentication, rate limit headers, and all Reddit API calls.
Free tier: 100 requests per minute per OAuth client.
"""

import time
from typing import Any, Optional

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import (APIKeyMissingError, AuthenticationError,
                                 CrawlError, RateLimitExceededError)


class RedditAPIClient:
    """
    Client for Reddit's official API via OAuth2.
    Monitors X-Ratelimit-* response headers for compliance.
    """

    AUTH_URL = "https://www.reddit.com/api/v1/access_token"
    BASE_URL = "https://oauth.reddit.com"

    def __init__(self):
        settings = get_settings()
        self.client_id = settings.reddit_client_id
        self.client_secret = settings.reddit_client_secret
        self.user_agent = settings.reddit_user_agent

        if not self.client_id or not self.client_secret:
            raise APIKeyMissingError(
                "reddit", "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET"
            )

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # Rate limit tracking from response headers
        self._rate_limit_remaining: float = 100
        self._rate_limit_reset: float = 0

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers={"User-Agent": self.user_agent},
        )

    async def _authenticate(self) -> None:
        """Obtain an OAuth2 access token using client credentials."""
        auth_client = httpx.AsyncClient(timeout=15.0)
        try:
            response = await auth_client.post(
                self.AUTH_URL,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            # Token typically expires in 3600 seconds
            self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60

            self._client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("Reddit OAuth token obtained successfully")

        except httpx.HTTPStatusError as e:
            raise AuthenticationError(
                "reddit", f"OAuth failed: {e.response.status_code}"
            )
        finally:
            await auth_client.aclose()

    async def _ensure_auth(self) -> None:
        """Ensure we have a valid access token."""
        if not self._access_token or time.time() >= self._token_expires_at:
            await self._authenticate()

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """Update rate limit tracking from response headers."""
        remaining = response.headers.get("X-Ratelimit-Remaining")
        reset = response.headers.get("X-Ratelimit-Reset")

        if remaining is not None:
            self._rate_limit_remaining = float(remaining)
        if reset is not None:
            self._rate_limit_reset = time.time() + float(reset)

        if self._rate_limit_remaining <= 2:
            logger.warning(
                f"Reddit rate limit nearly exhausted: {self._rate_limit_remaining} remaining, "
                f"resets in {float(reset or 0):.0f}s"
            )

    async def _request(
        self, method: str, endpoint: str, params: Optional[dict] = None
    ) -> dict:
        """Make an authenticated API request."""
        await self._ensure_auth()

        # Check rate limit
        if self._rate_limit_remaining <= 1 and time.time() < self._rate_limit_reset:
            wait_time = self._rate_limit_reset - time.time()
            raise RateLimitExceededError("reddit", retry_after=int(wait_time))

        try:
            response = await self._client.request(method, endpoint, params=params)
            self._update_rate_limits(response)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitExceededError("reddit", retry_after=retry_after)

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Reddit API error: {e.response.status_code} - {e.response.text}"
            )
            raise CrawlError("reddit", endpoint, str(e))

    async def search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        """
        Search Reddit posts.

        Args:
            query: Search query
            subreddit: Optional subreddit to search within
            sort: Sort order (relevance, hot, top, new, comments)
            time_filter: Time filter (hour, day, week, month, year, all)
            limit: Results per page (max 100)
            after: Pagination fullname anchor
        """
        if subreddit:
            endpoint = f"/r/{subreddit}/search"
        else:
            endpoint = "/search"

        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 100),
            "restrict_sr": "true" if subreddit else "false",
            "type": "link",
        }
        if after:
            params["after"] = after

        return await self._request("GET", endpoint, params=params)

    async def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        """Get posts from a subreddit."""
        params = {"limit": min(limit, 100)}
        if after:
            params["after"] = after

        return await self._request("GET", f"/r/{subreddit}/{sort}", params=params)

    async def get_user_posts(
        self,
        username: str,
        sort: str = "new",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        """Get posts submitted by a user."""
        params = {
            "sort": sort,
            "limit": min(limit, 100),
            "type": "links",
        }
        if after:
            params["after"] = after

        return await self._request("GET", f"/user/{username}/submitted", params=params)

    async def get_post_detail(self, subreddit: str, post_id: str) -> dict:
        """Get full post detail including comments."""
        return await self._request("GET", f"/r/{subreddit}/comments/{post_id}")

    async def get_comments(
        self,
        subreddit: str,
        post_id: str,
        sort: str = "best",
        limit: int = 50,
    ) -> dict:
        """Get comments for a post."""
        params = {
            "sort": sort,
            "limit": min(limit, 500),
            "depth": 3,
        }
        return await self._request(
            "GET", f"/r/{subreddit}/comments/{post_id}", params=params
        )

    async def get_user_info(self, username: str) -> dict:
        """Get user profile information."""
        return await self._request("GET", f"/user/{username}/about")

    @property
    def rate_limit_remaining(self) -> float:
        return self._rate_limit_remaining

    async def close(self) -> None:
        await self._client.aclose()
