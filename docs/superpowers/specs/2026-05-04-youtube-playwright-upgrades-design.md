# YouTube Playwright Crawler Upgrades Design

**Goal:** Refactor `PlaywrightYouTubeCrawler` to use `BrowserManager` for browser lifecycle management and ensure consistent privacy consent handling.

**Architecture:**
- Use `browser_manager` singleton for creating new pages.
- Centralize `goto` calls into a helper method `_goto_with_consent` that automatically handles YouTube's privacy consent popups.
- Remove internal browser/playwright state from the crawler.

## Proposed Changes

### 1. Update `PlaywrightYouTubeCrawler` constructor
- Remove `_playwright` and `_browser` initializations.
- Remove `_init_browser` method.

### 2. Helper Method: `_goto_with_consent`
- Encapsulate `page.goto(url, ...)` and `self._handle_consent(page)`.
- This ensures that every navigation attempt is followed by a check for the consent popup.

### 3. Refactor methods
- `search`, `get_post_detail`, and `get_comments` will now:
    - Call `await browser_manager.new_page()` to get a page.
    - Call `await self._goto_with_consent(page, url)` for navigation.
    - Ensure `page.close()` is called in `finally`.

### 4. Cleanup
- Update `close` method to do nothing (or just log) as `BrowserManager` handles the browser lifecycle.

## Testing Strategy
- Create `tests/test_playwright_youtube.py`.
- Mock `browser_manager` to verify it's called correctly.
- Mock `Page` and its methods (`goto`, `evaluate`, `close`) to verify the crawler's logic.
- Verify that `_handle_consent` is called after navigation.
