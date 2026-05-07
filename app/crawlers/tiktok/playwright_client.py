"""
Playwright-based TikTok Client.
Intercepts XHR/Fetch API responses by automating a headless browser.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.parse

from loguru import logger
from playwright.async_api import BrowserContext, Page, async_playwright

from app.core.config import get_settings

class PlaywrightTikTokClient:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # We will collect intercepted API responses here temporarily
        self.intercepted_data: List[Dict] = []
        
        self.stealth_path = Path(__file__).parent / "stealth.min.js"

    async def init_browser(self):
        """Initialize the headless Chromium browser with stealth."""
        if self.playwright is None:
            self.playwright = await async_playwright().start()
            
        if self.browser is None:
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )
            
        if self.context is None:
            settings = get_settings()
            proxy = {"server": settings.proxy_url} if settings.proxy_url else None
            
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                proxy=proxy
            )
            
            if self.stealth_path.exists():
                await self.context.add_init_script(path=str(self.stealth_path))
                
        if self.page is None:
            self.page = await self.context.new_page()

    async def _handle_response(self, response, target_url_fragment: str):
        """Intercept responses containing our target URL fragment."""
        if target_url_fragment in response.url and response.request.resource_type in ["fetch", "xhr"]:
            try:
                # Wait for response body, handle potentially 204 or empty responses
                if response.status == 200:
                    body = await response.json()
                    self.intercepted_data.append(body)
            except Exception:
                pass

    async def _scroll_to_bottom(self, max_scrolls: int = 5, delay: float = 2.0):
        """Simulate human scrolling to trigger lazy loading API requests."""
        for _ in range(max_scrolls):
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(delay)

    async def search_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        """
        Search TikTok via Playwright interception.
        """
        await self.init_browser()
        self.intercepted_data.clear()
        
        target_api = "/api/search/general/"
        
        # Setup listener
        async def on_response(response):
            await self._handle_response(response, target_api)
            
        self.page.on("response", on_response)
        
        url = f"https://www.tiktok.com/search?q={urllib.parse.quote(keyword)}"
        logger.info(f"[TikTok Playwright] Navigating to search: {url}")
        
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # Need to clear a possible captcha or login modal? We just scroll.
            scroll_count = (limit // 12) + 2  # TikTok loads ~12 items per page
            await self._scroll_to_bottom(max_scrolls=scroll_count, delay=3.0)
            
        except Exception as e:
            logger.warning(f"[TikTok Playwright] Search timeout or error: {e}")
            
        finally:
            self.page.remove_listener("response", on_response)
            
        # Parse all intercepted data
        videos = []
        for payload in self.intercepted_data:
            items = payload.get("data", [])
            for item in items:
                if item.get("type") == 1:  # Type 1 is video (aweme)
                    info = item.get("item", {})
                    if info:
                        videos.append(info)
                        
        logger.info(f"[TikTok Playwright] Intercepted {len(videos)} raw video items")
        return videos[:limit]

    async def get_comments(self, video_id: str, limit: int = 50, username: str = "tiktok") -> List[Dict]:
        """
        Get comments by navigating to the video URL and scrolling.
        """
        await self.init_browser()
        self.intercepted_data.clear()
        
        target_api = "/api/comment/list/"
        
        async def on_response(response):
            await self._handle_response(response, target_api)
            
        self.page.on("response", on_response)
        
        # Navigate to arbitrary user's video endpoint is enough to trigger comment loading
        # Because we only have video_id sometimes, we might need a dummy username.
        # Format: https://www.tiktok.com/@user/video/{video_id}
        url = f"https://www.tiktok.com/@{username}/video/{video_id}"
        
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # Scroll down to load comments
            scroll_count = (limit // 20) + 2
            await self._scroll_to_bottom(max_scrolls=scroll_count, delay=2.5)
        except Exception as e:
            logger.warning(f"[TikTok Playwright] Comments timeout or error: {e}")
        finally:
            self.page.remove_listener("response", on_response)
            
        comments = []
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
