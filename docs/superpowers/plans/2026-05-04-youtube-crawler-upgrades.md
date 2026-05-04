# YouTube Crawler Commercial Grade Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the YouTube crawler with Innertube API support, browser management, privacy consent handling, and auto-updating yt-dlp for production-grade reliability.

**Architecture:** 
1. Introduce `BrowserManager` for shared Playwright browser instances.
2. Implement `InnertubeClient` for high-performance comment extraction.
3. Enhance `YtdlpClient` with self-healing update logic.
4. Refactor `PlaywrightYouTubeCrawler` to use these new components and handle EU privacy popups.

**Tech Stack:** Python, Playwright, yt-dlp, FastAPI/Pydantic, httpx

---

### Task 1: Core Configuration and Browser Manager

**Files:**
- Modify: `app/core/config.py`
- Create: `app/core/browser_manager.py`
- Create: `tests/test_browser_manager.py`

- [ ] **Step 1: Add new settings to `Settings`**
Add `youtube_cookies_file` and `playwright_browser_count`.

```python
    # app/core/config.py
    youtube_cookies_file: Optional[str] = None
    playwright_browser_count: int = 3
```

- [ ] **Step 2: Implement `BrowserManager`**
A singleton to manage Playwright browser instances and contexts.

```python
# app/core/browser_manager.py
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger

class BrowserManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance._playwright = None
            cls._instance._browser = None
        return cls._instance

    async def get_browser(self) -> Browser:
        if not self._browser:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def new_page(self, **kwargs) -> Page:
        browser = await self.get_browser()
        context = await browser.new_context(**kwargs)
        return await context.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

browser_manager = BrowserManager()
```

- [ ] **Step 3: Write test for `BrowserManager`**
Verify it can launch a page and close.

- [ ] **Step 4: Commit**

---

### Task 2: yt-dlp Auto-Update Mechanism

**Files:**
- Modify: `app/crawlers/youtube/ytdlp_client.py`
- Create: `tests/test_ytdlp_update.py`

- [ ] **Step 1: Add `_auto_update_ytdlp` to `YtdlpClient`**
Detect signature errors or outdated version messages in stderr and run upgrade.

```python
# app/crawlers/youtube/ytdlp_client.py
    async def _auto_update_ytdlp(self):
        logger.info("Attempting to auto-update yt-dlp...")
        try:
            import subprocess
            process = await asyncio.create_subprocess_exec(
                "pip", "install", "--upgrade", "yt-dlp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            logger.info("yt-dlp update completed.")
        except Exception as e:
            logger.error(f"Failed to update yt-dlp: {e}")
```

- [ ] **Step 2: Integrate into `_run_command`**
Trigger on specific error strings like "outdated" or "signature".

- [ ] **Step 3: Commit**

---

### Task 3: Innertube API for Comments

**Files:**
- Create: `app/crawlers/youtube/innertube_client.py`
- Modify: `app/crawlers/youtube/playwright_crawler.py`
- Create: `tests/test_innertube.py`

- [ ] **Step 1: Implement `InnertubeClient`**
Logic to extract API key and fetch comments via `v1/next`.

```python
# app/crawlers/youtube/innertube_client.py
import httpx
import re
import json
from app.crawlers.base import CommentResult

class InnertubeClient:
    def __init__(self):
        self.base_url = "https://www.youtube.com/youtubei/v1"
        self.client = httpx.AsyncClient()

    async def get_comments(self, video_id: str, limit: int = 100):
        # Implementation to get initial token and fetch pages
        pass
```

- [ ] **Step 2: Update `PlaywrightYouTubeCrawler.get_comments`**
Delegate to `InnertubeClient` for massive performance gains.

- [ ] **Step 3: Commit**

---

### Task 4: Privacy Consent and Browser Reuse in Playwright

**Files:**
- Modify: `app/crawlers/youtube/playwright_crawler.py`

- [ ] **Step 1: Use `browser_manager` in `PlaywrightYouTubeCrawler`**
Replace local `_init_browser` with `browser_manager`.

- [ ] **Step 2: Ensure `_handle_consent` is called**
Call it in `search` and `get_post_detail` after `page.goto`.

- [ ] **Step 3: Verify and Commit**
Check that browser instances are reused and popups are clicked.
