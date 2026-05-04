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
