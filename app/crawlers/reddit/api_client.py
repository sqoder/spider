"""
Reddit API Client — supports both Official OAuth2 API and No-API Public Scraper Mode.
If REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are missing, it automatically switches to
No-API mode, appending `.json` to public paths and utilizing browser-like headers.
"""

import time
import asyncio
from typing import Any, Optional

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError, CrawlError


class RedditAPIClient:
    """
    Client for Reddit's API.
    Auto-detects credentials and switches between OAuth and Public Scraper mode.
    """

    AUTH_URL = "https://www.reddit.com/api/v1/access_token"
    
    def __init__(self):
        settings = get_settings()
        self.client_id = settings.reddit_client_id
        self.client_secret = settings.reddit_client_secret
        
        # Check if we should use official OAuth or fallback to Public Scraper mode
        if self.client_id and self.client_secret:
            self.use_oauth = True
            self.base_url = "https://oauth.reddit.com"
            self.user_agent = settings.reddit_user_agent or "GlobalMediaCrawler/1.0"
            logger.info("[Reddit] Credentials detected. Using official OAuth API.")
        else:
            self.use_oauth = False
            self.base_url = "https://www.reddit.com"
            # Use a robust browser User-Agent to prevent 429/403 blocks in public mode
            self.user_agent = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
            logger.info("[Reddit] No credentials found. Automatically falling back to Public Scraper (.json) mode!")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # Rate limit tracking
        self._rate_limit_remaining: float = 100
        self._rate_limit_reset: float = 0
        self._last_request_time: float = 0.0

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

    # ------------------------------------------------------------------ auth

    async def _authenticate(self) -> None:
        """Obtain an OAuth2 access token (only used in OAuth mode)."""
        if not self.use_oauth:
            return

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
            self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60

            self._client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("[Reddit] OAuth token obtained successfully")

        except httpx.HTTPStatusError as e:
            logger.error(f"[Reddit] Authentication failed: {e.response.status_code}")
        finally:
            await auth_client.aclose()

    async def _ensure_auth(self) -> None:
        if self.use_oauth:
            if not self._access_token or time.time() >= self._token_expires_at:
                await self._authenticate()

    def _update_rate_limits(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-Ratelimit-Remaining")
        reset = response.headers.get("X-Ratelimit-Reset")

        if remaining is not None:
            self._rate_limit_remaining = float(remaining)
        if reset is not None:
            self._rate_limit_reset = time.time() + float(reset)

    async def _request(
        self, method: str, endpoint: str, params: Optional[dict] = None
    ) -> Any:
        """Make an API request. Appends .json in No-API mode. Includes retries."""
        await self._ensure_auth()

        # Check rate limits in OAuth mode
        if self.use_oauth and self._rate_limit_remaining <= 1 and time.time() < self._rate_limit_reset:
            wait_time = self._rate_limit_reset - time.time()
            raise RateLimitExceededError("reddit", retry_after=int(wait_time))

        # Check rate limits in No-API mode (1.5s interval to avoid 429)
        if not self.use_oauth:
            elapsed = time.time() - self._last_request_time
            if elapsed < 1.5:
                await asyncio.sleep(1.5 - elapsed)
            self._last_request_time = time.time()

        # Prepare No-API endpoint formatting (e.g. /search -> /search.json)
        url_path = endpoint
        if not self.use_oauth:
            if "?" in url_path:
                path_part, query_part = url_path.split("?", 1)
                url_path = f"{path_part}.json?{query_part}"
            else:
                url_path = f"{url_path}.json"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._client.request(method, url_path, params=params)
                if self.use_oauth:
                    self._update_rate_limits(response)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitExceededError("reddit", retry_after=retry_after)

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                # Retry on 5xx or specific errors
                if attempt < max_retries - 1 and e.response.status_code >= 500:
                    delay = 2 ** attempt
                    logger.debug(f"[Reddit] HTTP {e.response.status_code} - Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                
                logger.error(
                    f"[Reddit] HTTP Error: {e.response.status_code} - {e.response.text[:300]}"
                )
                raise CrawlError("reddit", endpoint, f"HTTP {e.response.status_code}")
                
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.debug(f"[Reddit] Network error ({e}) - Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                logger.error(f"[Reddit] Network Error: {e}")
                raise CrawlError("reddit", endpoint, str(e))

    # ------------------------------------------------------------------ search

    async def search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        endpoint = f"/r/{subreddit}/search" if subreddit else "/search"
        params: dict = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 100),
            "restrict_sr": "true" if subreddit else "false",
            "type": "link",
            "raw_json": 1,
        }
        if after:
            params["after"] = after
        return await self._request("GET", endpoint, params=params)

    # ------------------------------------------------------------------ subreddit

    async def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        params: dict = {"limit": min(limit, 100), "raw_json": 1}
        if after:
            params["after"] = after
        return await self._request("GET", f"/r/{subreddit}/{sort}", params=params)

    async def get_subreddit_info(self, subreddit: str) -> dict:
        return await self._request("GET", f"/r/{subreddit}/about")

    async def get_subreddit_rules(self, subreddit: str) -> dict:
        # Rules API doesn't support public JSON cleanly, return empty or try about in No-API
        if not self.use_oauth:
            return {"rules": []}
        return await self._request("GET", f"/r/{subreddit}/about/rules")

    # ------------------------------------------------------------------ posts

    async def get_post_detail(
        self,
        subreddit: str,
        post_id: str,
        comment_sort: str = "best",
        comment_limit: int = 500,
        comment_depth: int = 10,
    ) -> Any:
        params = {
            "sort": comment_sort,
            "limit": min(comment_limit, 500),
            "depth": comment_depth,
            "raw_json": 1,
        }
        return await self._request(
            "GET", f"/r/{subreddit}/comments/{post_id}", params=params
        )

    async def get_more_children(
        self, link_id: str, children: list[str], sort: str = "best"
    ) -> dict:
        # expansion of morechildren requires authenticated POST/GET usually
        if not self.use_oauth:
            return {"json": {"data": {"things": []}}}
        params = {
            "api_type": "json",
            "link_id": link_id,
            "children": ",".join(children[:100]),
            "sort": sort,
            "raw_json": 1,
        }
        return await self._request("GET", "/api/morechildren", params=params)

    # ------------------------------------------------------------------ comments

    async def get_comments(
        self,
        subreddit: str,
        post_id: str,
        sort: str = "best",
        limit: int = 500,
        depth: int = 10,
    ) -> Any:
        params = {
            "sort": sort,
            "limit": min(limit, 500),
            "depth": depth,
            "raw_json": 1,
        }
        return await self._request(
            "GET", f"/r/{subreddit}/comments/{post_id}", params=params
        )

    # ------------------------------------------------------------------ users

    async def get_user_info(self, username: str) -> dict:
        return await self._request("GET", f"/user/{username}/about")

    async def get_user_posts(
        self,
        username: str,
        sort: str = "new",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        params: dict = {
            "sort": sort,
            "limit": min(limit, 100),
            "type": "links",
            "raw_json": 1,
        }
        if after:
            params["after"] = after
        return await self._request("GET", f"/user/{username}/submitted", params=params)

    async def get_user_comments(
        self,
        username: str,
        sort: str = "new",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        params: dict = {
            "sort": sort,
            "limit": min(limit, 100),
            "raw_json": 1,
        }
        if after:
            params["after"] = after
        return await self._request("GET", f"/user/{username}/comments", params=params)

    async def get_user_trophies(self, username: str) -> dict:
        if not self.use_oauth:
            return {"data": {"trophies": []}}
        return await self._request("GET", f"/api/v1/user/{username}/trophies")

    # ------------------------------------------------------------------ batch

    async def get_posts_by_ids(self, fullnames: list[str]) -> dict:
        if not self.use_oauth:
            return {"data": {"children": []}}
        params = {"id": ",".join(fullnames[:100]), "raw_json": 1}
        return await self._request("GET", "/api/info", params=params)

    # ------------------------------------------------------------------ properties

    @property
    def rate_limit_remaining(self) -> float:
        return self._rate_limit_remaining

    async def close(self) -> None:
        await self._client.aclose()
