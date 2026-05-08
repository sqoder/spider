import json
from typing import Any
import asyncio

from loguru import logger
from scrapling import StealthyFetcher
from playwright.async_api import Response

from app.core.config import get_settings
from app.core.browser_manager import browser_manager


class TikTokPlaywrightClient:
    """
    Intercepts XHR/Fetch API responses by automating a headless browser with StealthyFetcher.
    """

    def __init__(self):
        self.settings = get_settings()
        self.fetcher: StealthyFetcher | None = None
        self._responses: dict[str, list[dict[str, Any]]] = {
            "search": [],
            "user_posts": [],
            "comments": [],
            "detail": [],
        }

    async def _init_browser(self):
        """Initialize the StealthyFetcher via BrowserManager."""
        if not self.fetcher:
            self.fetcher = await browser_manager.new_fetcher(
                cookies_file=self.settings.tiktok_cookies_file,
                headless=self.settings.playwright_headless,
            )

    async def close(self):
        if self.fetcher:
            await browser_manager.close_fetcher(self.fetcher)
            self.fetcher = None
            
    async def _handle_response(self, response: Response):
        """Playwright response interceptor."""
        url = response.url
        try:
            if "api/search/item" in url:
                data = await response.json()
                self._responses["search"].append(data)
            elif "api/post/item_list" in url:
                data = await response.json()
                self._responses["user_posts"].append(data)
            elif "api/comment/list" in url or "api/comment/list/reply" in url:
                data = await response.json()
                self._responses["comments"].append(data)
            elif "api/item/detail" in url:
                data = await response.json()
                self._responses["detail"].append(data)
        except Exception:
            pass  # Not JSON or failed to parse

    async def search(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Search TikTok via StealthyFetcher interception.
        """
        await self._init_browser()
        if not self.fetcher:
            return []
            
        page = getattr(self.fetcher, "page", None)
        if not page:
            # force page init
            await self.fetcher.get("https://www.tiktok.com/")
            page = getattr(self.fetcher, "page", None)

        if not page:
            return []

        # StealthyFetcher has access to the playwright page via .page
        page.on("response", self._handle_response)

        url = f"https://www.tiktok.com/search/video?q={keyword}"
        await page.goto(url, wait_until="domcontentloaded")

        # Scroll to trigger lazy loading
        items_collected = 0
        for _ in range(10):
            # Check responses collected so far
            for resp in self._responses["search"]:
                items = resp.get("item_list", [])
                items_collected += len(items)

            if items_collected >= limit:
                break

            await page.evaluate("window.scrollBy(0, window.innerHeight);")
            await asyncio.sleep(2)

        page.remove_listener("response", self._handle_response)

        results = []
        for resp in self._responses["search"]:
            results.extend(resp.get("item_list", []))

        self._responses["search"].clear()
        return results[:limit]

    # Note: user_posts, get_comments, get_detail could be implemented similarly
    # by navigating to the respective URLs and scrolling, then aggregating self._responses.
