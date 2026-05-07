# Project Quality Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current fast-moving crawler prototype into a maintainable, verifiable, high-quality Python project with one clear execution model, green tests, clean repository hygiene, and enforceable quality gates.

**Architecture:** Keep the existing crawler/result/repository strengths, but remove stale paths and route all execution through a small shared service layer. API routes, CLI scripts, and Celery workers must call the same orchestration code instead of each owning separate crawl/store/media logic.

**Tech Stack:** Python 3.11/3.12 target, FastAPI, SQLAlchemy async, pytest, pytest-asyncio, ruff, mypy or pyright, GitHub Actions, Scrapling 0.4.7, yt-dlp, gallery-dl, optional Playwright.

---

## Current Baseline

Run these commands before making any code changes. Save the output in the PR or commit notes.

- [ ] Confirm branch and working tree.

```bash
git status --short
git branch --show-current
```

Expected:
- Current branch is visible.
- Any existing unrelated changes are noted before starting.
- Do not reset or discard user changes.

- [ ] Run the current test suite.

```bash
venv/bin/python -m pytest
```

Expected current baseline:
- The suite collects 71 tests.
- 61 tests pass.
- 10 tests fail.
- Failures are concentrated in:
  - `tests/test_browser_manager.py`
  - `tests/test_innertube.py`
  - `tests/test_playwright_youtube.py`
  - `tests/test_reddit.py`

- [ ] Confirm syntax import baseline.

```bash
venv/bin/python -m compileall -q app tests
venv/bin/python - <<'PY'
import importlib
import pathlib

errors = []
for path in pathlib.Path("app").rglob("*.py"):
    if path.name == "__init__.py":
        continue
    module = ".".join(path.with_suffix("").parts)
    try:
        importlib.import_module(module)
    except Exception as exc:
        errors.append((module, type(exc).__name__, str(exc)))

for module, exc_type, message in errors:
    print(f"{module}: {exc_type}: {message}")
print(f"errors={len(errors)}")
PY
```

Expected current baseline:
- `compileall` exits 0.
- Import scan reports `app.storage.postgres` failing because it imports missing `TaskStatus`.

---

## Target Quality Bar

The remediation is complete only when all of these are true:

- [ ] `venv/bin/python -m pytest` exits 0.
- [ ] `venv/bin/python -m ruff check app tests` exits 0.
- [ ] `venv/bin/python -m ruff format --check app tests` exits 0.
- [ ] Static typing check exits 0 for the selected checker:
  - preferred: `venv/bin/python -m pyright app tests`
  - acceptable first step: `venv/bin/python -m mypy app`
- [ ] Import scan reports `errors=0`.
- [ ] README setup instructions can be followed on a clean machine.
- [ ] There is one shared crawl orchestration path used by API, CLI, and worker.
- [ ] No obsolete storage modules remain importable-but-broken.
- [ ] CI runs tests, lint, format check, import scan, and type check.

---

## File Responsibility Map

Use this map to prevent another round of drift.

- `app/crawlers/base.py`
  - Owns platform-neutral result contracts: `CrawlResult`, `CommentResult`, `BaseCrawler`.
- `app/crawlers/factory.py`
  - Owns platform registration and platform-to-crawler selection.
  - It should not contain task orchestration or storage policy.
- `app/services/crawl_service.py`
  - Create this file.
  - Owns direct crawl execution for search/detail/user/comment flows.
  - API routes, CLI, and worker should call this.
- `app/services/media_service.py`
  - Create this file if media logic remains more than one function.
  - Owns media download dispatch across YouTube, TikTok, Reddit, Instagram, X.
- `app/storage/base_store.py`
  - Owns store interface.
- `app/storage/file_store_impl.py`
  - Owns file export for jsonl/json/csv/excel.
- `app/storage/db_store_impl.py`
  - Owns database persistence using repositories.
- `app/storage/factory.py`
  - Owns config-to-store selection only.
- `app/storage/postgres.py`
  - Delete after confirming no live imports.
- `app/storage/file_storage.py`
  - Delete after confirming no live imports.
- `app/api/routes/crawl.py`
  - Thin HTTP wrapper around `crawl_service`.
- `app/workers/crawler_worker.py`
  - Thin Celery wrapper around `crawl_service`.
- `run.py`
  - Either remove, or convert into a tiny CLI wrapper around `crawl_service`.
- `config.py`
  - Either remove, or rename to an explicit local example such as `crawler_config.example.py`.
  - Runtime configuration should come from `app/core/config.py` and `.env`.
- `pyproject.toml`
  - Owns pytest, ruff, package metadata, and type checker config.
- `.github/workflows/pytest.yml`
  - Replace with a broader quality workflow.
- `README.md`
  - Must describe the actual supported setup paths.

---

## Phase 1: Repository Hygiene And Tooling

### Task 1: Create A Clean Baseline Commit

**Files:**
- Inspect only: entire repository

- [ ] Step 1: Record current tracked and ignored files.

```bash
git status --short --ignored
git ls-files | rg '(__pycache__|\.pyc$|\.env$|\.env\.sqlite$|crawler\.db|venv/|data/|\.pytest_cache|\.coverage|\.idea)'
```

Expected:
- Generated files are ignored.
- Only `.env.example` may appear from the second command.
- If anything else appears, remove it from Git tracking with `git rm --cached <path>` before continuing.

- [ ] Step 2: Confirm no secrets are tracked.

```bash
git ls-files | rg '(^\.env$|cookies|token|secret|password|crawler\.db)'
```

Expected:
- No real `.env`, cookie file, database, token, or password file is tracked.
- `.env.example` is allowed.

- [ ] Step 3: Commit repository hygiene only if tracked generated files were removed.

```bash
git add .gitignore
git status --short
git commit -m "Stabilize repository hygiene before quality remediation

Remove generated files from version control so future quality checks run
against source files only.

Confidence: high
Scope-risk: narrow
Tested: git status --short --ignored
Not-tested: full pytest suite unchanged by hygiene-only cleanup"
```

Expected:
- Commit is only needed if files changed.
- Commit message follows the Lore protocol.

### Task 2: Add Quality Tooling Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements-base.txt` or create a dev requirements file
- Modify: `.github/workflows/pytest.yml`

- [ ] Step 1: Add ruff and one type checker to development dependencies.

Recommended first pass:

```txt
ruff>=0.8.0
pyright>=1.1.390
```

If keeping all requirements in existing files, add these to `requirements-base.txt`. If splitting dev tools, create `requirements-dev.txt`:

```txt
-r requirements-base.txt
pytest>=8.3.0
pytest-asyncio>=0.24.0
pytest-cov>=5.0.0
ruff>=0.8.0
pyright>=1.1.390
```

- [ ] Step 2: Expand `pyproject.toml` with tool config.

Use this as the initial config:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py311"
line-length = 100
exclude = [
  ".git",
  ".venv",
  "venv",
  "__pycache__",
  ".pytest_cache",
  ".omx",
  "data",
  "media",
  "output",
]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "ASYNC", "SIM"]
ignore = [
  "E501",
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"

[tool.pyright]
pythonVersion = "3.11"
typeCheckingMode = "basic"
include = ["app", "tests"]
exclude = [
  "venv",
  ".venv",
  ".omx",
  "data",
  "media",
  "output",
]
```

- [ ] Step 3: Install dev dependencies.

```bash
venv/bin/python -m pip install -r requirements-base.txt
venv/bin/python -m pip install ruff pyright
```

Expected:
- Both commands exit 0.
- `venv/bin/python -m ruff --version` prints a version.
- `venv/bin/python -m pyright --version` prints a version.

- [ ] Step 4: Run tools and capture initial failures.

```bash
venv/bin/python -m ruff check app tests
venv/bin/python -m ruff format --check app tests
venv/bin/python -m pyright app tests
```

Expected:
- These may fail on first run.
- Save the failure categories.
- Do not mix broad formatting with behavior fixes in the same commit.

- [ ] Step 5: Commit only tooling/config changes.

```bash
git add pyproject.toml requirements-base.txt requirements-dev.txt .github/workflows/pytest.yml
git commit -m "Add enforceable local quality gates

Introduce lint, format, and type-check configuration so the project has
repeatable quality checks instead of relying on manual review.

Confidence: high
Scope-risk: narrow
Tested: venv/bin/python -m ruff --version; venv/bin/python -m pyright --version
Not-tested: full suite may still fail until contract drift is fixed"
```

Expected:
- Commit includes only tooling changes.

---

## Phase 2: Fix Broken Tests And Contract Drift

### Task 3: Decide And Lock BrowserManager Contract

**Decision:** Keep the Scrapling `StealthyFetcher` contract. Do not restore Playwright `Page` as the primary abstraction unless the project intentionally drops Scrapling for visible browser crawling.

**Files:**
- Modify: `app/core/browser_manager.py`
- Modify: `tests/test_browser_manager.py`
- Modify: `tests/test_playwright_youtube.py`
- Inspect: `app/crawlers/youtube/playwright_crawler.py`
- Inspect: `app/crawlers/youtube/visible_crawler.py`
- Inspect: `app/crawlers/tiktok/playwright_client.py`

- [ ] Step 1: Replace old Page-based tests with Fetcher-based tests.

`tests/test_browser_manager.py` should validate:
- singleton behavior
- semaphore acquisition and release
- `close_fetcher()` calls `quit()` or `close()`
- missing cookie file returns empty cookies
- existing cookie file is parsed and cached

Minimum test outline:

```python
import pytest

from app.core.browser_manager import BrowserManager


class FakeFetcher:
    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


@pytest.mark.asyncio
async def test_close_fetcher_releases_slot(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSER_COUNT", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    manager = BrowserManager()
    manager._fetchers = []
    manager._semaphore = None

    fake = FakeFetcher()
    manager._fetchers.append(fake)
    await manager._get_semaphore().acquire()

    await manager.close_fetcher(fake)

    assert fake.quit_called is True
    assert fake not in manager._fetchers
    assert manager._get_semaphore()._value == 1
```

- [ ] Step 2: Update `tests/test_playwright_youtube.py` to patch `new_fetcher`, not `new_page`.

Minimum mock shape:

```python
class FakeFetcher:
    def __init__(self, page):
        self.page = page


@pytest.mark.asyncio
async def test_search_uses_browser_manager():
    crawler = PlaywrightYouTubeCrawler()
    with patch("app.crawlers.youtube.playwright_crawler.browser_manager") as mock_bm:
        mock_page = AsyncMock()
        mock_fetcher = FakeFetcher(mock_page)
        mock_bm.new_fetcher = AsyncMock(return_value=mock_fetcher)
        mock_bm.close_fetcher = AsyncMock()
        mock_page.evaluate.return_value = {
            "contents": {
                "twoColumnSearchResultsRenderer": {
                    "primaryContents": {
                        "sectionListRenderer": {
                            "contents": []
                        }
                    }
                }
            }
        }

        await crawler.search("test")

        mock_bm.new_fetcher.assert_awaited_once()
        mock_page.goto.assert_awaited()
        mock_bm.close_fetcher.assert_awaited_once_with(mock_fetcher)
```

- [ ] Step 3: Ensure crawler code closes fetchers consistently.

Search:

```bash
rg -n "new_fetcher|close_context|close_fetcher|new_page" app tests
```

Expected after edits:
- No crawler calls `browser_manager.new_page`.
- New code closes Scrapling fetchers with `close_fetcher`.
- `close_context` may remain only as compatibility support, not as the primary path.

- [ ] Step 4: Run focused tests.

```bash
venv/bin/python -m pytest tests/test_browser_manager.py tests/test_playwright_youtube.py -v
```

Expected:
- All tests in both files pass.
- No `Page` type assertion remains.

- [ ] Step 5: Commit browser contract fix.

```bash
git add app/core/browser_manager.py tests/test_browser_manager.py tests/test_playwright_youtube.py app/crawlers/youtube/playwright_crawler.py
git commit -m "Align browser tests with Scrapling fetcher contract

Browser management now exposes Scrapling fetchers rather than raw
Playwright pages, so tests and crawler cleanup paths are updated around
the current abstraction.

Rejected: Restore raw Playwright Page as the primary return type | the codebase already migrated crawler paths to Scrapling fetchers
Confidence: high
Scope-risk: moderate
Tested: venv/bin/python -m pytest tests/test_browser_manager.py tests/test_playwright_youtube.py -v
Not-tested: live YouTube browser crawl"
```

### Task 4: Fix Innertube Client Test Drift

**Files:**
- Modify: `tests/test_innertube.py`
- Optional modify: `app/crawlers/youtube/innertube_client.py`

- [ ] Step 1: Update the test to patch `client.fetcher.get`.

Replace old reference:

```python
patch.object(client.client, "get", return_value=MagicMock(text=mock_html))
```

with:

```python
patch.object(client.fetcher, "get", return_value=MagicMock(text=mock_html))
```

- [ ] Step 2: Make context extraction test match current parser behavior.

If `_extract_json()` cannot parse the current `ytcfg.set` JSON shape, add a focused test first:

```python
def test_extract_json_from_ytcfg_context():
    client = InnertubeClient()
    html = 'ytcfg.set({"INNERTUBE_API_KEY":"test_key","INNERTUBE_CONTEXT":{"client":{"clientName":"WEB"}}});'
    context = client._extract_json(html, r'["\\']INNERTUBE_CONTEXT["\\']\\s*:\\s*\\{')
    assert context == {"client": {"clientName": "WEB"}}
```

Then adjust `_extract_json()` only if the test proves it is broken.

- [ ] Step 3: Run focused tests.

```bash
venv/bin/python -m pytest tests/test_innertube.py -v
```

Expected:
- `test_innertube_extraction` passes.
- `test_parse_comment_data` still passes.

- [ ] Step 4: Commit Innertube fix.

```bash
git add tests/test_innertube.py app/crawlers/youtube/innertube_client.py
git commit -m "Repair Innertube tests around current fetcher API

The Innertube client owns a Scrapling fetcher, not the previous client
attribute, so tests now patch the live dependency surface.

Confidence: high
Scope-risk: narrow
Tested: venv/bin/python -m pytest tests/test_innertube.py -v
Not-tested: live YouTube Innertube request"
```

### Task 5: Restore Or Expose Reddit URL Parsing Contract

**Decision:** Preserve backwards compatibility by exposing `RedditCrawler._extract_post_info()` as a static method that delegates to `_extract_post_ids()`.

**Files:**
- Modify: `app/crawlers/reddit/crawler.py`
- Verify: `tests/test_reddit.py`

- [ ] Step 1: Add compatibility method inside `RedditCrawler`.

Add this near the top of the class:

```python
    @staticmethod
    def _extract_post_info(url: str) -> tuple[str, str]:
        """Backward-compatible URL parser used by tests and older callers."""
        return _extract_post_ids(url)
```

- [ ] Step 2: Strengthen `_extract_post_ids()` regex to accept old/new Reddit and hyphenated subreddit names.

Replace:

```python
match = re.search(r"reddit\.com/r/([\w]+)/comments/([\w]+)", url)
```

with:

```python
match = re.search(r"(?:old\\.)?reddit\\.com/r/([A-Za-z0-9_]+)/comments/([A-Za-z0-9_]+)", url)
```

If hyphenated subreddit names must be supported, use:

```python
match = re.search(r"(?:old\\.)?reddit\\.com/r/([A-Za-z0-9_-]+)/comments/([A-Za-z0-9_]+)", url)
```

- [ ] Step 3: Run focused tests.

```bash
venv/bin/python -m pytest tests/test_reddit.py -v
```

Expected:
- All Reddit URL parsing tests pass.

- [ ] Step 4: Commit Reddit parser compatibility.

```bash
git add app/crawlers/reddit/crawler.py tests/test_reddit.py
git commit -m "Preserve Reddit URL parser compatibility

Expose the old parser method as a thin compatibility wrapper while the
implementation remains module-level and shared by the crawler.

Confidence: high
Scope-risk: narrow
Tested: venv/bin/python -m pytest tests/test_reddit.py -v
Not-tested: live Reddit API requests"
```

### Task 6: Run Full Test Suite After Contract Fixes

**Files:**
- No direct edits unless failures remain.

- [ ] Step 1: Run full tests.

```bash
venv/bin/python -m pytest
```

Expected:
- 71 collected.
- 71 passed.
- If new failures appear, stop and fix the specific contract before continuing.

- [ ] Step 2: Run import scan.

```bash
venv/bin/python - <<'PY'
import importlib
import pathlib

errors = []
for path in pathlib.Path("app").rglob("*.py"):
    if path.name == "__init__.py":
        continue
    module = ".".join(path.with_suffix("").parts)
    try:
        importlib.import_module(module)
    except Exception as exc:
        errors.append((module, type(exc).__name__, str(exc)))

for module, exc_type, message in errors:
    print(f"{module}: {exc_type}: {message}")
print(f"errors={len(errors)}")
PY
```

Expected at this point:
- `errors=1` may still remain for `app.storage.postgres`.
- That is handled in Phase 3.

---

## Phase 3: Delete Or Repair Dead Storage Paths

### Task 7: Remove Broken `app/storage/postgres.py`

**Decision:** Delete `app/storage/postgres.py` unless there is a current live caller that truly needs it. The active DB storage path is `DbStoreImplement` plus repositories.

**Files:**
- Delete: `app/storage/postgres.py`
- Verify: `app/storage/db_store_impl.py`
- Verify: `app/repositories/*.py`

- [ ] Step 1: Confirm no live imports.

```bash
rg -n "from app\\.storage\\.postgres|import app\\.storage\\.postgres|PostgresStorage" app tests run.py
```

Expected:
- Only `app/storage/postgres.py` itself appears, or no results.
- If other files import it, migrate those imports to repositories or `DbStoreImplement` first.

- [ ] Step 2: Delete the file.

```bash
git rm app/storage/postgres.py
```

- [ ] Step 3: Run import scan.

```bash
venv/bin/python - <<'PY'
import importlib
import pathlib

errors = []
for path in pathlib.Path("app").rglob("*.py"):
    if path.name == "__init__.py":
        continue
    module = ".".join(path.with_suffix("").parts)
    try:
        importlib.import_module(module)
    except Exception as exc:
        errors.append((module, type(exc).__name__, str(exc)))

for module, exc_type, message in errors:
    print(f"{module}: {exc_type}: {message}")
print(f"errors={len(errors)}")
PY
```

Expected:
- `errors=0`.

- [ ] Step 4: Run DB storage tests.

```bash
venv/bin/python -m pytest tests/test_visible_storage.py tests/test_api.py -v
```

Expected:
- Tests pass.
- No import references to deleted storage remain.

- [ ] Step 5: Commit deletion.

```bash
git add app/storage/postgres.py
git commit -m "Remove obsolete PostgreSQL storage path

The live database persistence path uses DbStoreImplement and repositories.
The old PostgresStorage module referenced removed model fields and failed
on import, so deleting it removes a misleading broken API.

Rejected: Patch PostgresStorage in place | duplicate DB storage abstractions would preserve the current confusion
Confidence: high
Scope-risk: narrow
Tested: import scan errors=0; venv/bin/python -m pytest tests/test_visible_storage.py tests/test_api.py -v
Not-tested: production PostgreSQL migration run"
```

### Task 8: Remove Or Merge `app/storage/file_storage.py`

**Decision:** Prefer deleting `file_storage.py` after confirming it has no live callers. Keep `FileStoreImplement` as the only file export implementation.

**Files:**
- Delete: `app/storage/file_storage.py`
- Verify: `app/storage/file_store_impl.py`
- Verify: `app/storage/factory.py`

- [ ] Step 1: Confirm no live imports.

```bash
rg -n "file_storage|FileStorage\\(|from app\\.storage\\.file_storage" app tests run.py
```

Expected:
- Only `app/storage/file_storage.py` appears.
- If callers exist, migrate them to `StoreFactory.create_store(platform, crawler_type)`.

- [ ] Step 2: Delete unused implementation.

```bash
git rm app/storage/file_storage.py
```

- [ ] Step 3: Add or update file store tests.

Create focused tests in `tests/test_file_store.py`:

```python
import json

import pytest

from app.core.config import get_settings
from app.storage.file_store_impl import FileStoreImplement


@pytest.mark.asyncio
async def test_jsonl_store_writes_content(tmp_path, monkeypatch):
    monkeypatch.setenv("SAVE_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("SAVE_DATA_OPTION", "jsonl")
    monkeypatch.delenv("SAVE_DATA_SUBDIR", raising=False)
    get_settings.cache_clear()

    store = FileStoreImplement("youtube", "search", "jsonl")
    await store.store_content([{"source_id": "v1", "title": "Video"}])

    path = tmp_path / "youtube" / "jsonl" / "search_contents.jsonl"
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"source_id": "v1", "title": "Video"}]
```

- [ ] Step 4: Run storage tests.

```bash
venv/bin/python -m pytest tests/test_file_store.py tests/test_visible_storage.py -v
```

Expected:
- All selected tests pass.

- [ ] Step 5: Commit storage cleanup.

```bash
git add app/storage/file_storage.py tests/test_file_store.py
git commit -m "Keep one file storage implementation

FileStoreImplement is the active storage interface used by StoreFactory,
so the unused FileStorage module is removed and the remaining JSONL path
is covered with a focused regression test.

Rejected: Keep both implementations | duplicate file export paths invite drift
Confidence: high
Scope-risk: narrow
Tested: venv/bin/python -m pytest tests/test_file_store.py tests/test_visible_storage.py -v
Not-tested: Excel export path"
```

---

## Phase 4: Unify Execution Through A Shared Service

### Task 9: Create `app/services/crawl_service.py`

**Files:**
- Create: `app/services/crawl_service.py`
- Modify: `app/services/__init__.py`
- Test: `tests/test_crawl_service.py`

**Design:** This service owns the direct crawl flow once. API, CLI, and worker call it.

- [ ] Step 1: Write tests first.

Create `tests/test_crawl_service.py`:

```python
import pytest

from app.crawlers.base import CommentResult, CrawlResult
from app.services.crawl_service import CrawlDetailResponse, CrawlService


class FakeCrawler:
    def __init__(self):
        self.closed = False

    async def search(self, keyword: str, limit: int = 20):
        return [
            CrawlResult(
                platform="youtube",
                source_id="vid1",
                title="Test Video",
                url="https://youtube.com/watch?v=vid1",
            )
        ]

    async def get_post_detail(self, url: str):
        return CrawlResult(
            platform="youtube",
            source_id="vid1",
            title="Detail",
            url=url,
        )

    async def get_comments(self, post_id: str, limit: int = 50):
        return [
            CommentResult(
                platform="youtube",
                source_id="comment1",
                content="hello",
            )
        ]

    async def close(self):
        self.closed = True


class FakeStore:
    def __init__(self):
        self.content = []
        self.comments = []
        self.closed = False

    async def store_content(self, items):
        self.content.extend(items)

    async def store_comment(self, post_id, items):
        self.comments.append((post_id, items))

    async def store_creator(self, items):
        pass

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_search_stores_and_returns_items():
    crawler = FakeCrawler()
    store = FakeStore()
    service = CrawlService(
        crawler_factory=lambda platform: crawler,
        store_factory=lambda platform, task_type: store,
    )

    result = await service.search("youtube", "AI", limit=10)

    assert result.platform == "youtube"
    assert result.keyword == "AI"
    assert result.count == 1
    assert store.content[0]["source_id"] == "vid1"
    assert store.closed is True
    assert crawler.closed is True


@pytest.mark.asyncio
async def test_detail_stores_comments_when_requested():
    crawler = FakeCrawler()
    store = FakeStore()
    service = CrawlService(
        crawler_factory=lambda platform: crawler,
        store_factory=lambda platform, task_type: store,
    )

    result = await service.detail(
        "youtube",
        "https://youtube.com/watch?v=vid1",
        comments_limit=5,
    )

    assert isinstance(result, CrawlDetailResponse)
    assert result.data["source_id"] == "vid1"
    assert result.comments[0]["source_id"] == "comment1"
    assert store.comments[0][0] == "vid1"
```

- [ ] Step 2: Run tests and verify they fail because service does not exist.

```bash
venv/bin/python -m pytest tests/test_crawl_service.py -v
```

Expected:
- FAIL with `ModuleNotFoundError` or import error for `app.services.crawl_service`.

- [ ] Step 3: Implement service.

Create `app/services/crawl_service.py`:

```python
from dataclasses import dataclass
from typing import Callable

from loguru import logger

from app.crawlers.base import BaseCrawler
from app.crawlers.factory import CrawlerFactory
from app.storage.base_store import BaseStore
from app.storage.factory import StoreFactory


CrawlerFactoryFn = Callable[[str], BaseCrawler]
StoreFactoryFn = Callable[[str, str], BaseStore]


@dataclass(slots=True)
class CrawlSearchResponse:
    platform: str
    keyword: str
    count: int
    items: list[dict]


@dataclass(slots=True)
class CrawlDetailResponse:
    platform: str
    data: dict
    comments: list[dict]


class CrawlService:
    def __init__(
        self,
        crawler_factory: CrawlerFactoryFn | None = None,
        store_factory: StoreFactoryFn | None = None,
    ):
        self._crawler_factory = crawler_factory or CrawlerFactory.create
        self._store_factory = store_factory or StoreFactory.create_store

    async def search(self, platform: str, keyword: str, limit: int = 20) -> CrawlSearchResponse:
        crawler = self._crawler_factory(platform)
        try:
            results = await crawler.search(keyword, limit=limit)
            result_dicts = [result.to_dict() for result in results]

            store = self._store_factory(platform, "search")
            try:
                await store.store_content(result_dicts)
            finally:
                await store.close()

            return CrawlSearchResponse(
                platform=platform,
                keyword=keyword,
                count=len(result_dicts),
                items=result_dicts,
            )
        finally:
            await crawler.close()

    async def detail(
        self,
        platform: str,
        url: str,
        comments_limit: int = 0,
    ) -> CrawlDetailResponse:
        crawler = self._crawler_factory(platform)
        try:
            result = await crawler.get_post_detail(url)
            result_dict = result.to_dict()

            comments = []
            if comments_limit > 0:
                try:
                    comments = await crawler.get_comments(result.source_id, limit=comments_limit)
                except Exception as exc:
                    logger.warning(f"Failed to fetch comments for {result.source_id}: {exc}")

            comment_dicts = [comment.to_dict() for comment in comments]

            store = self._store_factory(platform, "detail")
            try:
                await store.store_content([result_dict])
                if comment_dicts:
                    await store.store_comment(result.source_id, comment_dicts)
            finally:
                await store.close()

            return CrawlDetailResponse(
                platform=platform,
                data=result_dict,
                comments=comment_dicts,
            )
        finally:
            await crawler.close()
```

- [ ] Step 4: Run service tests.

```bash
venv/bin/python -m pytest tests/test_crawl_service.py -v
```

Expected:
- Tests pass.

- [ ] Step 5: Commit service.

```bash
git add app/services/crawl_service.py app/services/__init__.py tests/test_crawl_service.py
git commit -m "Centralize direct crawl orchestration

Introduce CrawlService so HTTP routes, CLI flows, and workers can share
the same crawler/store lifecycle instead of duplicating crawl logic.

Confidence: high
Scope-risk: moderate
Tested: venv/bin/python -m pytest tests/test_crawl_service.py -v
Not-tested: live platform crawling"
```

### Task 10: Convert API Crawl Routes To The Service

**Files:**
- Modify: `app/api/routes/crawl.py`
- Modify: `tests/test_api.py`

- [ ] Step 1: Update route implementation.

Replace direct `CrawlerFactory`/`StoreFactory` usage with:

```python
from app.services.crawl_service import CrawlService
```

Route shape:

```python
@router.post("/search")
async def crawl_search(request: SearchRequest):
    platform = request.platform.value if hasattr(request.platform, "value") else request.platform
    result = await CrawlService().search(platform, request.keyword, limit=request.limit)
    return {
        "platform": result.platform,
        "keyword": result.keyword,
        "count": result.count,
        "items": result.items,
    }
```

Detail route shape:

```python
@router.post("/detail")
async def crawl_detail(request: DetailRequest):
    platform = request.platform.value if hasattr(request.platform, "value") else request.platform
    result = await CrawlService().detail(
        platform,
        request.url,
        comments_limit=request.comments_limit,
    )
    return {
        "platform": result.platform,
        "data": result.data,
        "comments": result.comments,
    }
```

- [ ] Step 2: Update API tests to patch service methods.

Patch:

```python
with patch("app.api.routes.crawl.CrawlService") as service_cls:
```

Use `AsyncMock` on `.search` and `.detail`.

- [ ] Step 3: Run API tests.

```bash
venv/bin/python -m pytest tests/test_api.py tests/test_crawl_service.py -v
```

Expected:
- All selected tests pass.
- API tests do not patch `CrawlerFactory` directly anymore.

- [ ] Step 4: Commit API conversion.

```bash
git add app/api/routes/crawl.py tests/test_api.py
git commit -m "Route crawl API through shared service

The HTTP layer now delegates crawl execution to CrawlService, keeping
request handling thin and aligning it with other execution surfaces.

Confidence: high
Scope-risk: moderate
Tested: venv/bin/python -m pytest tests/test_api.py tests/test_crawl_service.py -v
Not-tested: live HTTP crawl against external platforms"
```

### Task 11: Convert Worker To The Service Or Split Worker-Specific Persistence

**Files:**
- Modify: `app/workers/crawler_worker.py`
- Test: create or update `tests/test_worker.py`

**Decision:** The worker can keep task status updates, but actual crawling and storage should go through shared service functions. If task-specific DB updates require a separate method, add it to `CrawlService` as `execute_task_from_model(task)`.

- [ ] Step 1: Write worker tests around status transitions.

Minimum test goals:
- missing task returns without crashing
- successful task marks success
- crawler failure marks failed
- crawler is closed

- [ ] Step 2: Extract large `_execute_task_async()` branches into small helpers.

Target helper names:

```python
async def _run_task_crawl(task, crawler):
    if task.task_type == "search":
        return await crawler.search(task.keyword, limit=task.limit_count), {}
    if task.task_type == "user_posts":
        return await crawler.get_user_posts(task.username, limit=task.limit_count), {}
    if task.task_type in ("post_detail", "url_parse"):
        result = await crawler.get_post_detail(task.url)
        comments = await crawler.get_comments(result.source_id, limit=task.limit_count)
        return [result], {result.source_id: comments}
    if task.task_type == "comments":
        comments = await crawler.get_comments((task.params or {}).get("post_id", ""), limit=task.limit_count)
        return [], {"comments": comments}
    raise ValueError(f"Unsupported task type: {task.task_type}")

async def _store_task_results(task, results, comments_by_post):
    from app.storage.factory import StoreFactory

    store = StoreFactory.create_store(task.platform, task.task_type)
    try:
        if results:
            await store.store_content([result.to_dict() for result in results])
        for post_id, comments in comments_by_post.items():
            if comments and post_id != "comments":
                await store.store_comment(post_id, [comment.to_dict() for comment in comments])
    finally:
        await store.close()
```

Expected:
- `_execute_task_async()` becomes an orchestration function under 90 lines.
- Branches for `search`, `user_posts`, `post_detail`, `comments` are easy to test.

- [ ] Step 3: Run worker tests.

```bash
venv/bin/python -m pytest tests/test_worker.py -v
```

Expected:
- Worker-specific tests pass without Redis/Celery running.

- [ ] Step 4: Run full API/storage tests.

```bash
venv/bin/python -m pytest tests/test_api.py tests/test_visible_storage.py tests/test_crawl_service.py tests/test_worker.py -v
```

Expected:
- All selected tests pass.

- [ ] Step 5: Commit worker conversion.

```bash
git add app/workers/crawler_worker.py tests/test_worker.py app/services/crawl_service.py
git commit -m "Share crawl orchestration with worker execution

Worker task status handling remains worker-owned, while crawling and
storage behavior moves toward the same service path used by HTTP routes.

Confidence: medium
Scope-risk: moderate
Tested: venv/bin/python -m pytest tests/test_api.py tests/test_visible_storage.py tests/test_crawl_service.py tests/test_worker.py -v
Not-tested: live Celery worker against Redis"
```

---

## Phase 5: Rationalize CLI And Configuration

### Task 12: Decide The Fate Of `run.py`

**Decision:** Keep a CLI only if it is a thin wrapper around service code. The current `run.py` should not directly mutate environment variables and duplicate media/storage orchestration.

**Files:**
- Modify or delete: `run.py`
- Modify or rename: `config.py`
- Modify: `README.md`
- Test: `tests/test_cli_runner.py` if keeping CLI

- [ ] Step 1: Choose one of two paths.

Path A, recommended:
- Replace `run.py` with a thin CLI wrapper.
- Move user examples from `config.py` into `examples/crawler_config.example.py` or README.
- Runtime settings come from `.env` and CLI flags.

Path B, acceptable for personal scripts:
- Move `run.py` and `config.py` into `examples/`.
- Make it clear they are not production entrypoints.

- [ ] Step 2A: If keeping CLI, define arguments.

Supported minimum:

```bash
venv/bin/python run.py search --platform youtube --keyword "AI" --limit 5
venv/bin/python run.py detail --platform youtube --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --comments-limit 50
```

- [ ] Step 3A: Add CLI parser tests.

Create `tests/test_cli_runner.py` with tests that patch `CrawlService` and assert command parsing only.

Expected:
- Tests never hit real external websites.

- [ ] Step 4A: Run CLI tests.

```bash
venv/bin/python -m pytest tests/test_cli_runner.py -v
```

Expected:
- CLI tests pass.

- [ ] Step 2B: If moving to examples, run import scan.

```bash
mkdir -p examples
git mv run.py examples/run_personal_crawl.py
git mv config.py examples/crawler_config.example.py
venv/bin/python -m compileall -q app tests
```

Expected:
- App and tests compile.
- No production module imports `config.py`.

- [ ] Step 5: Commit CLI/config cleanup.

```bash
git add run.py config.py examples README.md tests/test_cli_runner.py
git commit -m "Clarify supported crawl entrypoints

The project now has one production orchestration path, with any personal
runner behavior either routed through the service layer or moved into
examples.

Rejected: Keep run.py as a parallel orchestrator | duplicated crawl, storage, and media paths caused drift
Confidence: medium
Scope-risk: moderate
Tested: venv/bin/python -m pytest tests/test_cli_runner.py -v; venv/bin/python -m compileall -q app tests
Not-tested: live personal crawler run"
```

---

## Phase 6: Documentation And Setup Reality Check

### Task 13: Fix README Setup Instructions

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Add if needed: `docker-compose.yml`
- Add if needed: `alembic.ini`

- [ ] Step 1: Decide supported local setup.

Supported setup must be one of:
- Simple mode with SQLite and file output.
- Full mode with PostgreSQL, Redis, and Celery.

Document both only if both are actually tested.

- [ ] Step 2: If README says `docker-compose up -d`, add a real compose file.

Minimum `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: crawler
      POSTGRES_PASSWORD: crawler_pass
      POSTGRES_DB: global_media_crawler
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

- [ ] Step 3: If README says `alembic upgrade head`, track `alembic.ini`.

Current `.gitignore` ignores `alembic.ini`. Change that only if `alembic.ini` is intended to be part of setup.

Expected:
- `git ls-files alembic.ini` shows the file if README depends on it.
- Otherwise README must not instruct users to run Alembic from a missing config.

- [ ] Step 4: Rewrite README commands to match reality.

Minimum simple mode:

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-base.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Minimum validation:

```bash
venv/bin/python -m pytest
curl http://localhost:8000/api/health
```

- [ ] Step 5: Run README commands in a clean shell where possible.

```bash
venv/bin/python -m pytest tests/test_api.py -v
```

Expected:
- API tests pass.

- [ ] Step 6: Commit docs/setup changes.

```bash
git add README.md .env.example docker-compose.yml alembic.ini .gitignore
git commit -m "Align setup documentation with runnable project paths

README instructions now describe only supported local setup flows and
include the configuration files those flows require.

Confidence: high
Scope-risk: narrow
Tested: venv/bin/python -m pytest tests/test_api.py -v
Not-tested: brand-new machine setup"
```

### Task 14: Move Planning Artifacts Out Of Runtime Docs Or Mark Them Clearly

**Files:**
- Inspect: `docs/superpowers/plans/*`
- Inspect: `docs/superpowers/specs/*`
- Modify: `README.md`

- [ ] Step 1: Decide whether `docs/superpowers` is project documentation or agent work history.

If it is work history:
- Keep it under `docs/superpowers/`.
- Add README note: "These are implementation planning artifacts, not user-facing documentation."

If it is not useful to users:
- Move it to `.omx/` or remove it from public documentation in a separate commit.

- [ ] Step 2: Verify no broken links.

```bash
rg -n "docs/superpowers|2026-05-04" README.md docs
```

Expected:
- Any references are intentional.

- [ ] Step 3: Commit documentation organization.

```bash
git add README.md docs/superpowers
git commit -m "Clarify planning artifacts versus user documentation

Separate implementation history from user-facing docs so contributors
can tell which documents are operational and which are historical.

Confidence: high
Scope-risk: narrow
Tested: rg -n \"docs/superpowers|2026-05-04\" README.md docs
Not-tested: rendered documentation site"
```

---

## Phase 7: Continuous Integration

### Task 15: Replace Minimal Pytest Workflow With Quality Workflow

**Files:**
- Modify: `.github/workflows/pytest.yml`

- [ ] Step 1: Update workflow to run on Python 3.11 and 3.12.

Use this shape:

```yaml
name: Quality

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-base.txt
          pip install ruff pyright

      - name: Compile
        run: python -m compileall -q app tests

      - name: Import scan
        run: |
          python - <<'PY'
          import importlib
          import pathlib

          errors = []
          for path in pathlib.Path("app").rglob("*.py"):
              if path.name == "__init__.py":
                  continue
              module = ".".join(path.with_suffix("").parts)
              try:
                  importlib.import_module(module)
              except Exception as exc:
                  errors.append((module, type(exc).__name__, str(exc)))

          for module, exc_type, message in errors:
              print(f"{module}: {exc_type}: {message}")
          if errors:
              raise SystemExit(1)
          PY

      - name: Ruff lint
        run: ruff check app tests

      - name: Ruff format
        run: ruff format --check app tests

      - name: Type check
        run: pyright app tests

      - name: Pytest
        run: pytest
```

- [ ] Step 2: Validate workflow syntax locally if `actionlint` is available.

```bash
command -v actionlint && actionlint .github/workflows/pytest.yml || true
```

Expected:
- If `actionlint` exists, no workflow syntax errors.
- If not installed, command exits 0 because of `|| true`; note that CI is the final workflow validator.

- [ ] Step 3: Commit CI workflow.

```bash
git add .github/workflows/pytest.yml
git commit -m "Run full quality gates in CI

CI now checks imports, formatting, lint, typing, and tests across the
supported Python versions so contract drift is caught before merge.

Confidence: high
Scope-risk: narrow
Tested: command -v actionlint && actionlint .github/workflows/pytest.yml || true
Not-tested: remote GitHub Actions execution"
```

---

## Phase 8: Lint, Format, And Type Cleanup

### Task 16: Apply Formatting In A Dedicated Commit

**Files:**
- Modify: many Python files, formatting only

- [ ] Step 1: Run formatter.

```bash
venv/bin/python -m ruff format app tests
```

Expected:
- Files may be reformatted.
- No behavior changes.

- [ ] Step 2: Verify formatting check.

```bash
venv/bin/python -m ruff format --check app tests
```

Expected:
- Exit 0.

- [ ] Step 3: Run tests after formatting.

```bash
venv/bin/python -m pytest
```

Expected:
- All tests pass.

- [ ] Step 4: Commit formatting only.

```bash
git add app tests
git commit -m "Normalize Python formatting

Apply the configured formatter in a dedicated commit so style churn is
isolated from behavior changes.

Confidence: high
Scope-risk: narrow
Tested: venv/bin/python -m ruff format --check app tests; venv/bin/python -m pytest
Not-tested: live crawler behavior"
```

### Task 17: Fix Lint Findings In Small Batches

**Files:**
- Modify: files reported by ruff

- [ ] Step 1: Run lint.

```bash
venv/bin/python -m ruff check app tests
```

Expected:
- Either exit 0 or print concrete file/line findings.

- [ ] Step 2: Fix one category at a time.

Recommended order:
- unused imports
- import sorting
- bare `except`
- overly broad `except Exception` where it hides real failures
- async misuse
- simplification rules

- [ ] Step 3: After each category, run:

```bash
venv/bin/python -m ruff check app tests
venv/bin/python -m pytest
```

Expected:
- Lint count decreases.
- Tests stay green.

- [ ] Step 4: Commit lint cleanup.

```bash
git add app tests
git commit -m "Resolve lint findings without behavior changes

Clean up import, exception, and simplification findings raised by ruff
while keeping crawler behavior covered by the existing tests.

Confidence: high
Scope-risk: moderate
Tested: venv/bin/python -m ruff check app tests; venv/bin/python -m pytest
Not-tested: live external platform calls"
```

### Task 18: Fix Type Checker Findings

**Files:**
- Modify: files reported by pyright or mypy

- [ ] Step 1: Run type checker.

```bash
venv/bin/python -m pyright app tests
```

Expected:
- Either exit 0 or print typed findings.

- [ ] Step 2: Fix type issues by improving contracts, not by hiding everything.

Allowed:
- add `Protocol` for injected fake factories
- make optional fields explicit
- narrow `Any`
- add return types
- use `cast()` only when runtime checks already prove the type

Avoid:
- file-wide ignores
- broad `# type: ignore`
- changing runtime behavior just to please the checker

- [ ] Step 3: Run type check and tests.

```bash
venv/bin/python -m pyright app tests
venv/bin/python -m pytest
```

Expected:
- Type checker exits 0.
- Tests pass.

- [ ] Step 4: Commit typing cleanup.

```bash
git add app tests pyproject.toml
git commit -m "Tighten basic type contracts

Resolve type checker findings by making service, storage, and crawler
interfaces explicit enough for automated checks to catch drift.

Confidence: medium
Scope-risk: moderate
Tested: venv/bin/python -m pyright app tests; venv/bin/python -m pytest
Not-tested: strict type-checking mode"
```

---

## Phase 9: Final Verification Gate

### Task 19: Run The Complete Local Quality Gate

**Files:**
- No edits unless a gate fails.

- [ ] Step 1: Run all required checks from a clean shell.

```bash
venv/bin/python -m compileall -q app tests
venv/bin/python - <<'PY'
import importlib
import pathlib

errors = []
for path in pathlib.Path("app").rglob("*.py"):
    if path.name == "__init__.py":
        continue
    module = ".".join(path.with_suffix("").parts)
    try:
        importlib.import_module(module)
    except Exception as exc:
        errors.append((module, type(exc).__name__, str(exc)))

for module, exc_type, message in errors:
    print(f"{module}: {exc_type}: {message}")
print(f"errors={len(errors)}")
raise SystemExit(1 if errors else 0)
PY
venv/bin/python -m ruff check app tests
venv/bin/python -m ruff format --check app tests
venv/bin/python -m pyright app tests
venv/bin/python -m pytest
```

Expected:
- `compileall` exits 0.
- Import scan prints `errors=0`.
- Ruff lint exits 0.
- Ruff format check exits 0.
- Pyright exits 0.
- Pytest exits 0.

- [ ] Step 2: Check repository status.

```bash
git status --short
```

Expected:
- Only intentional changes remain.
- No generated files are staged.

- [ ] Step 3: Write final remediation summary.

Create or update `docs/quality-report.md` with:

```markdown
# Quality Remediation Report

## Summary
- Tests:
- Lint:
- Format:
- Type check:
- Import scan:

## Removed Drift
- Deleted obsolete storage path:
- Unified execution through:
- Updated documentation:

## Remaining Risks
- Live platform behavior:
- Anti-bot/browser behavior:
- External API quota behavior:
```

- [ ] Step 4: Commit final report.

```bash
git add docs/quality-report.md
git commit -m "Document quality remediation evidence

Record the completed quality gates, removed drift, and remaining live
integration risks so future contributors know the project state.

Confidence: high
Scope-risk: narrow
Tested: full local quality gate
Not-tested: live external platform crawling"
```

---

## Optional Phase 10: Live Smoke Tests

Run these only after unit tests and static gates are green. These hit external services and may be flaky or rate-limited.

### Task 20: Smoke Test Local API

- [ ] Step 1: Start the API.

```bash
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected:
- Server starts without import errors.
- Logs show app startup.

- [ ] Step 2: Check health.

```bash
curl -s http://127.0.0.1:8000/api/health | python -m json.tool
```

Expected:
- JSON contains `"success": true`.
- `supported_platforms` is a list.

### Task 21: Smoke Test One Platform In Non-Destructive Mode

- [ ] Step 1: Use a low limit.

```bash
curl -s -X POST http://127.0.0.1:8000/api/crawl/search \
  -H 'Content-Type: application/json' \
  -d '{"platform":"youtube","keyword":"open source","limit":1}' \
  | python -m json.tool
```

Expected:
- Either one result is returned, or an external-service error is logged clearly.
- No unhandled traceback leaks to the client.

- [ ] Step 2: Record result in `docs/quality-report.md`.

Expected:
- Report states whether live smoke passed, failed due to environment, or was skipped.

---

## Execution Order Summary

Implement in this exact order:

1. Repository hygiene and quality tooling.
2. BrowserManager, Innertube, and Reddit test contract fixes.
3. Delete broken storage paths.
4. Create shared `CrawlService`.
5. Route API through the service.
6. Route worker or worker helper logic through the service.
7. Rationalize `run.py` and `config.py`.
8. Fix README/setup/CI.
9. Run formatting, lint, typing cleanup.
10. Run complete local quality gate.
11. Optionally run live smoke tests.

Do not start broad refactors before the tests are green. Do not add a new platform until the final quality gate passes.

---

## Self-Review Checklist For This Plan

- [x] The plan starts with the required agentic-worker header.
- [x] The plan names exact files to create, modify, inspect, or delete.
- [x] Each task has concrete commands and expected results.
- [x] Existing failing areas are handled explicitly: BrowserManager, Innertube, Playwright YouTube tests, Reddit parser tests, stale storage module.
- [x] The plan separates formatting, lint, typing, behavior fixes, docs, and CI into separate commits.
- [x] The plan includes the repository's Lore commit protocol in example commit messages.
- [x] The plan avoids adding new crawler features before quality gates are green.
