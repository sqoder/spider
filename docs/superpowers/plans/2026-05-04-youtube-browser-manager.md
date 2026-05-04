# YouTube Crawler Commercial Upgrade - Task 1: Browser Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize browser management using Playwright to reduce overhead and avoid memory leaks.

**Architecture:** Implement a singleton `BrowserManager` that maintains a shared Playwright instance and browser context. Add necessary configuration settings.

**Tech Stack:** Python, Playwright, Pytest, Pydantic Settings.

---

### Task 1.1: Update Configuration

**Files:**
- Modify: `app/core/config.py`
- Test: `tests/test_core.py`

- [ ] **Step 1: Write the failing test for new settings**

Add to `tests/test_core.py` in `TestConfig` class:

```python
    def test_youtube_crawler_settings(self):
        settings = Settings(_env_file=None)
        # Check default values for new settings
        assert hasattr(settings, "youtube_cookies_file")
        assert settings.playwright_browser_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core.py::TestConfig::test_youtube_crawler_settings -v`
Expected: FAIL with AttributeError or AssertionError.

- [ ] **Step 3: Update `Settings` in `app/core/config.py`**

```python
    # ---- YouTube ----
    youtube_api_key: Optional[str] = None
    youtube_daily_quota: int = 10000
    youtube_use_scraper: bool = True
    youtube_cookies_file: Optional[str] = None  # New
    playwright_browser_count: int = 3  # New
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_core.py::TestConfig::test_youtube_crawler_settings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py tests/test_core.py
git commit -m "feat: add youtube crawler configuration settings"
```

---

### Task 1.2: Implement BrowserManager

**Files:**
- Create: `app/core/browser_manager.py`
- Test: `tests/test_browser_manager.py`

- [ ] **Step 1: Write the failing test for `BrowserManager`**

Create `tests/test_browser_manager.py`:

```python
import pytest
from app.core.browser_manager import BrowserManager

@pytest.mark.asyncio
async def test_browser_manager_singleton():
    bm1 = BrowserManager()
    bm2 = BrowserManager()
    assert bm1 is bm2

@pytest.mark.asyncio
async def test_browser_manager_new_page():
    bm = BrowserManager()
    page = await bm.new_page()
    try:
        assert page is not None
        await page.goto("about:blank")
        assert page.url == "about:blank"
    finally:
        await bm.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_manager.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement `BrowserManager` in `app/core/browser_manager.py`**

```python
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

class BrowserManager:
    _instance: Optional["BrowserManager"] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance

    async def get_browser(self) -> Browser:
        if not self._browser:
            if not self._playwright:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Launched new Chromium browser instance")
        return self._browser

    async def new_page(self, **kwargs) -> Page:
        browser = await self.get_browser()
        # For now, we create a new context per page to isolate state, 
        # but keep the browser instance alive.
        context = await browser.new_context(**kwargs)
        return await context.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
            logger.info("Closed Chromium browser instance")
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("Stopped Playwright")

browser_manager = BrowserManager()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/browser_manager.py tests/test_browser_manager.py
git commit -m "feat: implement BrowserManager for centralized browser handling"
```
