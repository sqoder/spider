"""
Scrapling-based TikTok Client.
Intercepts XHR/Fetch API responses by automating a headless browser with StealthyFetcher.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.parse

from loguru import logger
from scrapling import StealthyFetcher

from app.core.config import get_settings
from app.core.browser_manager import browser_manager


class PlaywrightTikTokClient:
    def __init__(self):
        self.fetcher: Optional[StealthyFetcher] = None
        # We will collect intercepted API responses here temporarily
        self.intercepted_data: List[Dict] = []

    async def init_fetcher(self):
        """Initialize the StealthyFetcher via BrowserManager."""
        if self.fetcher is None:
            settings = get_settings()
            proxy = settings.proxy_url if settings.proxy_url else None

            self.fetcher = await browser_manager.new_fetcher(headless=True, proxy=proxy)
            # Scrapling StealthyFetcher doesn't need external stealth.min.js usually
            # as it has its own built-in stealth mechanisms.

    async def _scroll_to_bottom(self, max_scrolls: int = 5, delay: float = 2.0):
        """Simulate human scrolling using Scrapling's page evaluation."""
        for _ in range(max_scrolls):
            # StealthyFetcher has access to the playwright page via .page
            await self.fetcher.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(delay)

    async def _handle_response(self, response):
        """Internal callback for response interception."""
        # Note: In Scrapling, you can access the underlying playwright page to add listeners
        target_search = "/api/search/general/"
        target_comments = "/api/comment/list/"

        if (
            target_search in response.url or target_comments in response.url
        ) and response.request.resource_type in ["fetch", "xhr"]:
            try:
                if response.status == 200:
                    body = await response.json()
                    self.intercepted_data.append(body)
            except Exception:
                pass

    async def search_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        """
        Search TikTok via StealthyFetcher interception.
        """
        await self.init_fetcher()
        self.intercepted_data.clear()

        # Access raw playwright page to setup listener
        page = self.fetcher.page
        page.on("response", self._handle_response)

        url = f"https://www.tiktok.com/search?q={urllib.parse.quote(keyword)}"
        logger.info(f"[TikTok Scrapling] Navigating to search: {url}")

        try:
            # Use Scrapling's navigate-and-extract or just goto
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            scroll_count = (limit // 12) + 2
            await self._scroll_to_bottom(max_scrolls=scroll_count, delay=3.0)

        except Exception as e:
            logger.warning(f"[TikTok Scrapling] Search timeout or error: {e}")

        finally:
            page.remove_listener("response", self._handle_response)

        # Parse all intercepted data
        videos = []
        for payload in self.intercepted_data:
            items = payload.get("data", [])
            for item in items:
                if item.get("type") == 1:
                    info = item.get("item", {})
                    if info:
                        videos.append(info)

        logger.info(f"[TikTok Scrapling] Intercepted {len(videos)} raw video items")
        return videos[:limit]

    async def get_comments(
        self, video_id: str, limit: int = 50, username: str = "tiktok"
    ) -> List[Dict]:
        """
        Get comments by navigating to the video URL and scrolling.
        """
        await self.init_fetcher()
        self.intercepted_data.clear()

        page = self.fetcher.page
        page.on("response", self._handle_response)

        url = f"https://www.tiktok.com/@{username}/video/{video_id}"
        logger.info(f"[TikTok Scrapling] Navigating to video: {url}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            scroll_count = (limit // 20) + 2
            await self._scroll_to_bottom(max_scrolls=scroll_count, delay=2.5)
        except Exception as e:
            logger.warning(f"[TikTok Scrapling] Comments timeout or error: {e}")
        finally:
            page.remove_listener("response", self._handle_response)

        # Deduplicate and extract comments from intercepted payloads
        all_comments = []
        for payload in self.intercepted_data:
            comments_list = payload.get("comments", [])
            if comments_list:
                all_comments.extend(comments_list)

        return all_comments[:limit]

    async def close(self):
        """Close the fetcher via BrowserManager."""
        if self.fetcher:
            await browser_manager.close_fetcher(self.fetcher)
            self.fetcher = None

        for payload in self.intercepted_data:
            c_list = payload.get("comments", [])
            if c_list:
                comments.extend(c_list)

        return comments[:limit]

    async def close(self):
        """Cleanup browser resources."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
