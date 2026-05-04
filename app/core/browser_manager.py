# app/core/browser_manager.py
import asyncio
import os
import time
from typing import Optional, List, Dict, Tuple
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

class BrowserManager:
    _instance: Optional['BrowserManager'] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance._contexts = []
            cls._instance._cookie_cache: Dict[str, Tuple[float, List[Dict]]] = {}
        return cls._instance

    async def get_browser(self) -> Browser:
        if not self._browser:
            logger.info("Starting Playwright and launching Chromium...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    def _parse_cookies_file(self, filepath: str) -> List[Dict]:
        """Parse Netscape format cookies file into Playwright format. Results are cached by mtime."""
        current_mtime = os.path.getmtime(filepath) if os.path.exists(filepath) else 0
        if current_mtime:
            cached_mtime, cached = self._cookie_cache.get(filepath, (0, []))
            if cached_mtime == current_mtime:
                return cached

        cookies = []
        if not os.path.exists(filepath):
            return cookies

        try:
            with open(filepath, 'r') as f:
                for line in f:
                    if not line.strip() or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) < 7:
                        continue

                    cookies.append({
                        'name': parts[5].strip(),
                        'value': parts[6].strip(),
                        'domain': parts[0].strip(),
                        'path': parts[2].strip(),
                        'expires': int(parts[4].strip()) if parts[4].strip().isdigit() else -1,
                        'secure': parts[3].strip().upper() == 'TRUE',
                        'httpOnly': False,
                    })
            self._cookie_cache[filepath] = (current_mtime, cookies)
        except Exception as e:
            logger.error(f"Failed to parse cookies file: {e}")
        return cookies

    async def new_page(self, cookies_file: Optional[str] = None, **kwargs) -> Page:
        browser = await self.get_browser()

        cookies = []
        if cookies_file:
            cookies = self._parse_cookies_file(cookies_file)

        context = await browser.new_context(**kwargs)
        self._contexts.append(context)
        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"Injected {len(cookies)} cookies into new context.")
        return await context.new_page()

    async def close_context(self, page: Page) -> None:
        """Close a page and its associated browser context."""
        context = page.context
        await page.close()
        await context.close()
        try:
            self._contexts.remove(context)
        except ValueError:
            pass

    async def close_all_contexts(self) -> None:
        """Close all tracked browser contexts."""
        for ctx in self._contexts:
            try:
                await ctx.close()
            except Exception as e:
                logger.warning(f"Failed to close browser context: {e}")
        self._contexts.clear()

    async def close(self):
        await self.close_all_contexts()
        if self._browser:
            logger.info("Closing browser...")
            await self._browser.close()
            self._browser = None
        if self._playwright:
            logger.info("Stopping Playwright...")
            await self._playwright.stop()
            self._playwright = None

browser_manager = BrowserManager()
