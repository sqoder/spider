"""
Reddit API Client — supports both Official OAuth2 API and No-API Public Scraper Mode.
If REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are missing, it automatically switches to
No-API mode, appending `.json` to public paths and utilizing browser-like headers.
"""

import asyncio
import time
from typing import Any

from loguru import logger
from scrapling import Fetcher

from app.core.config import get_settings
from app.core.exceptions import CrawlError, RateLimitExceededError


class RedditAPIClient:
    """
    Client for Reddit's API.
    Auto-detects credentials and switches between OAuth and Public Scraper mode.
    Uses Scrapling Fetcher for advanced anti-bot evasion and HTTP/3.
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
            logger.info(
                "[Reddit] No credentials found. Automatically falling back to Public Scraper (.json) mode!"
            )

        self._access_token: str | None = None
        self._token_expires_at: float = 0

        # Rate limit tracking
        self._rate_limit_remaining: float = 100
        self._rate_limit_reset: float = 0
        self._last_request_time: float = 0.0

        # Scrapling Fetcher initialization
        self._fetcher = Fetcher(
            user_agent=self.user_agent,
            timeout=30000,  # Scrapling uses ms
        )

    # ------------------------------------------------------------------ auth

    async def _authenticate(self) -> None:
        """Obtain an OAuth2 access token (only used in OAuth mode)."""
        if not self.use_oauth:
            return

        try:
            # Using temporary fetcher for auth to avoid messing with main fetcher headers
            auth_fetcher = Fetcher(timeout=15000)
            response = auth_fetcher.post(
                self.AUTH_URL,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self.user_agent},
            )

            if response.status_code != 200:
                logger.error(f"[Reddit] Authentication failed: {response.status_code}")
                return

            data = response.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60

            logger.info("[Reddit] OAuth token obtained successfully")

        except Exception as e:
            logger.error(f"[Reddit] Authentication error: {e}")

    async def _ensure_auth(self) -> None:
        if self.use_oauth and (not self._access_token or time.time() >= self._token_expires_at):
            await self._authenticate()

    def _update_rate_limits(self, response) -> None:
        remaining = response.headers.get("X-Ratelimit-Remaining")
        reset = response.headers.get("X-Ratelimit-Reset")

        if remaining is not None:
            self._rate_limit_remaining = float(remaining)
        if reset is not None:
            self._rate_limit_reset = time.time() + float(reset)

    async def _request(self, method: str, endpoint: str, params: dict | None = None) -> Any:
        """Make an API request using Scrapling Fetcher."""
        await self._ensure_auth()

        # Check rate limits in OAuth mode
        if (
            self.use_oauth
            and self._rate_limit_remaining <= 1
            and time.time() < self._rate_limit_reset
        ):
            wait_time = self._rate_limit_reset - time.time()
            raise RateLimitExceededError("reddit", retry_after=int(wait_time))

        # Check rate limits in No-API mode (1.5s interval to avoid 429)
        if not self.use_oauth:
            elapsed = time.time() - self._last_request_time
            if elapsed < 1.5:
                await asyncio.sleep(1.5 - elapsed)
            self._last_request_time = time.time()

        # Prepare URL
        url = f"{self.base_url}{endpoint}"
        if not self.use_oauth:
            if "?" in url:
                path_part, query_part = url.split("?", 1)
                url = f"{path_part}.json?{query_part}"
            else:
                url = f"{url}.json"

        headers = {}
        if self.use_oauth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Scrapling Fetcher is synchronous in current version or provides async?
                # Actually Scrapling Fetcher calls are usually blocking,
                # but we are in an async context.
                # Let's check if Scrapling has an async fetcher.
                # If not, we run in executor.

                def _do_fetch():
                    return self._fetcher.request(
                        method=method, url=url, params=params, headers=headers
                    )

                response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

                if self.use_oauth:
                    self._update_rate_limits(response)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitExceededError("reddit", retry_after=retry_after)

                if response.status_code >= 400:
                    logger.warning(
                        f"[Reddit] Request failed with {response.status_code}: {response.text[:100]}"
                    )
                    if attempt < max_retries - 1 and response.status_code >= 500:
                        await asyncio.sleep(2**attempt)
                        continue
                    response.raise_for_status()

                return response.json()

            except Exception as e:
                if isinstance(e, RateLimitExceededError):
                    raise
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                logger.error(f"[Reddit] Request error: {e}")
                raise CrawlError("reddit", endpoint, str(e)) from e

    async def aclose(self):
        # Scrapling Fetcher doesn't have an explicit aclose usually,
        # but good practice to define it if we move to sessions later.
        pass

    # ------------------------------------------------------------------ search

    async def search(
        self,
        query: str,
        subreddit: str | None = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
        after: str | None = None,
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
        after: str | None = None,
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
        return await self._request("GET", f"/r/{subreddit}/comments/{post_id}", params=params)

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
        return await self._request("GET", f"/r/{subreddit}/comments/{post_id}", params=params)

    # ------------------------------------------------------------------ users

    async def get_user_info(self, username: str) -> dict:
        return await self._request("GET", f"/user/{username}/about")

    async def get_user_posts(
        self,
        username: str,
        sort: str = "new",
        limit: int = 25,
        after: str | None = None,
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
        after: str | None = None,
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
