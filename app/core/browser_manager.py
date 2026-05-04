# app/core/browser_manager.py
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright
from loguru import logger

class BrowserManager:
    _instance: Optional['BrowserManager'] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance

    async def get_browser(self) -> Browser:
        if not self._browser:
            logger.info("Starting Playwright and launching Chromium...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def new_page(self, **kwargs) -> Page:
        browser = await self.get_browser()
        # Create a new context for each page to ensure isolation
        context = await browser.new_context(**kwargs)
        return await context.new_page()

    async def close(self):
        if self._browser:
            logger.info("Closing browser...")
            await self._browser.close()
            self._browser = None
        if self._playwright:
            logger.info("Stopping Playwright...")
            await self._playwright.stop()
            self._playwright = None

browser_manager = BrowserManager()
