# BrowserManager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a singleton `BrowserManager` to centrally manage Playwright browser instances and contexts, supporting the YouTube crawler upgrades.

**Architecture:** A singleton class that manages a single Playwright instance and a Chromium browser instance. It provides methods to create new pages and handle graceful shutdown.

**Tech Stack:** Playwright (async), Python, Loguru, Pytest (async).

---

### Task 1: Implement BrowserManager

**Files:**
- Create: `app/core/browser_manager.py`
- Test: `tests/test_browser_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browser_manager.py
import pytest
from app.core.browser_manager import browser_manager
from playwright.async_api import Page

@pytest.mark.asyncio
async def test_browser_manager_lifecycle():
    # Test new_page creates a valid page
    page = await browser_manager.new_page()
    assert isinstance(page, Page)
    assert not page.is_closed()
    
    # Test singleton behavior
    from app.core.browser_manager import BrowserManager
    bm2 = BrowserManager()
    assert browser_manager is bm2
    
    # Cleanup
    await browser_manager.close()
    assert browser_manager._browser is None
    assert browser_manager._playwright is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.browser_manager'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/browser_manager.py tests/test_browser_manager.py
git commit -m "feat: implement BrowserManager for centralized browser handling"
```
