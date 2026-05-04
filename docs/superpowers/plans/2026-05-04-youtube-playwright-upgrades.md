# YouTube Playwright Crawler Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `PlaywrightYouTubeCrawler` to use `BrowserManager` and handle privacy consent consistently.

**Architecture:**
- Integrate `BrowserManager` for page creation.
- Implement `_goto_with_consent` for robust navigation.
- Decouple crawler from browser lifecycle.

**Tech Stack:** Python, Playwright, Pytest

---

### Task 1: Create Test Suite for PlaywrightYouTubeCrawler

**Files:**
- Create: `tests/test_playwright_youtube.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.youtube.playwright_crawler import PlaywrightYouTubeCrawler

@pytest.mark.asyncio
async def test_search_uses_browser_manager():
    crawler = PlaywrightYouTubeCrawler()
    with patch("app.crawlers.youtube.playwright_crawler.browser_manager") as mock_bm:
        mock_page = AsyncMock()
        mock_bm.new_page.return_value = mock_page
        
        # We need to mock ytInitialData evaluation
        mock_page.evaluate.return_value = {"contents": {}} 
        
        await crawler.search("test")
        
        mock_bm.new_page.assert_called_once()
        mock_page.goto.assert_called()
        mock_page.close.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playwright_youtube.py -v`
Expected: FAIL (AttributeError because `browser_manager` is not yet imported/used, or it fails because it tries to use its own `_init_browser`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_playwright_youtube.py
git commit -m "test: add initial test for PlaywrightYouTubeCrawler"
```

### Task 2: Refactor PlaywrightYouTubeCrawler to use BrowserManager

**Files:**
- Modify: `app/crawlers/youtube/playwright_crawler.py`

- [ ] **Step 1: Update imports and __init__**

```python
from app.core.browser_manager import browser_manager

# ... in PlaywrightYouTubeCrawler ...
    def __init__(self):
        super().__init__()
        # Remove self._playwright and self._browser
```

- [ ] **Step 2: Implement _goto_with_consent and refactor methods**

```python
    async def _goto_with_consent(self, page, url):
        await page.goto(url, wait_until="domcontentloaded")
        await self._handle_consent(page)

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        page = await browser_manager.new_page(
            locale="en-US",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        try:
            url = f"https://www.youtube.com/results?search_query={keyword}"
            await self._goto_with_consent(page, url)
            # ... rest of search ...
```

- [ ] **Step 3: Run tests to verify it passes**

Run: `pytest tests/test_playwright_youtube.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/crawlers/youtube/playwright_crawler.py
git commit -m "refactor: use BrowserManager in PlaywrightYouTubeCrawler"
```

### Task 3: Complete Refactoring and Cleanup

**Files:**
- Modify: `app/crawlers/youtube/playwright_crawler.py`

- [ ] **Step 1: Refactor get_post_detail and get_comments**
- [ ] **Step 2: Remove _init_browser and update close**
- [ ] **Step 3: Verify all tests**

Run: `pytest tests/test_playwright_youtube.py tests/test_youtube.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/crawlers/youtube/playwright_crawler.py
git commit -m "feat: complete PlaywrightYouTubeCrawler upgrades"
```
