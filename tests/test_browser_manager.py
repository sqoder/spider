# tests/test_browser_manager.py
import pytest
from app.core.config import get_settings
from app.core.browser_manager import BrowserManager, browser_manager
from playwright.async_api import Page


class FakePage:
    def __init__(self, context):
        self.context = context
        self.closed = False

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self):
        self.closed = False

    async def new_page(self):
        return FakePage(self)

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, context):
        self.context = context

    async def new_context(self, **kwargs):
        return self.context

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


@pytest.mark.asyncio
async def test_browser_manager_releases_context_slot(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSER_COUNT", "1")
    get_settings.cache_clear()
    manager = BrowserManager()
    context = FakeContext()
    manager._browser = FakeBrowser(context)
    manager._playwright = None
    manager._contexts = []
    manager._context_semaphore = None
    manager._context_semaphore_limit = None

    page = await manager.new_page()

    assert manager._context_semaphore._value == 0
    assert manager._contexts == [context]

    await manager.close_context(page)

    assert page.closed is True
    assert context.closed is True
    assert manager._contexts == []
    assert manager._context_semaphore._value == 1

    manager._browser = None
    manager._context_semaphore = None
    manager._context_semaphore_limit = None
