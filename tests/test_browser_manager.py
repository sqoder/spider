# tests/test_browser_manager.py
import pytest

from app.core.browser_manager import BrowserManager, browser_manager
from app.core.config import get_settings


class FakeFetcher:
    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


@pytest.mark.asyncio
async def test_browser_manager_singleton():
    bm2 = BrowserManager()
    assert browser_manager is bm2


@pytest.mark.asyncio
async def test_close_fetcher_releases_slot(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSER_COUNT", "1")
    get_settings.cache_clear()
    manager = BrowserManager()
    manager._fetchers = []
    manager._semaphore = None

    fake = FakeFetcher()
    manager._fetchers.append(fake)
    await manager._get_semaphore().acquire()

    assert manager._get_semaphore()._value == 0

    await manager.close_fetcher(fake)

    assert fake.quit_called is True
    assert fake not in manager._fetchers
    assert manager._get_semaphore()._value == 1


@pytest.mark.asyncio
async def test_parse_cookies_file_missing():
    # Test that missing cookie file returns empty cookies and doesn't crash
    cookies = browser_manager._parse_cookies_file("non_existent_file.txt")
    assert cookies == []
