# YouTube & Reddit Crawler Fix Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining bug fixes and optimizations for YouTube and Reddit crawlers, specifically focusing on unifying the Reddit API client to use `httpx` and ensuring config defaults are fully synced.

**Architecture:**
- Standardize `RedditAPIClient` on `httpx` for all network calls to ensure consistency, better proxy support, and maturity as recommended in the latest version of the construction order.
- Ensure `app/core/config.py` correctly consumes all relevant defaults from `crawler_config.py`.

**Tech Stack:** Python 3.11, httpx, pydantic-settings, loguru

---

### Task 1: Refactor Reddit API Client to use httpx

**Files:**
- Modify: `app/crawlers/reddit/api_client.py`

- [ ] **Step 1: Update `_authenticate` to use `httpx`**
Replace Scrapling Fetcher with `httpx.Client` and use `status_code`.

- [ ] **Step 2: Update `_request` to use `httpx`**
Modify the `_do_fetch` closure to use `httpx.Client` with proxy support. Update all `response.status` checks to `response.status_code`.

- [ ] **Step 3: Update `get_more_children` to use `httpx`**
Ensure the No-API fallback also uses the updated `_request`.

### Task 2: Sync Remaining Config Fields

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Check for missing fields from `crawler_config.py`**
Verify fields like `COMMENTS_SORT`, `CONCURRENT_LIMIT` (mapping to `playwright_browser_count`), and any others are correctly initialized from `_cfg`.

- [ ] **Step 2: Apply fixes to `Settings` defaults**

### Task 3: Final Verification

**Files:**
- Create: `verify_completion.py` (temporary test script)

- [ ] **Step 1: Run YouTube search and comment verification**
- [ ] **Step 2: Run Reddit search and more_children expansion verification**
- [ ] **Step 3: Confirm no `DeprecationWarning` for `get_event_loop` in YouTube/Reddit API paths**
