import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.youtube.playwright_crawler import PlaywrightYouTubeCrawler

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

        # We need to mock ytInitialData evaluation
        mock_page.evaluate.return_value = {"contents": {"twoColumnSearchResultsRenderer": {"primaryContents": {"sectionListRenderer": {"contents": []}}}}}

        await crawler.search("test")

        mock_bm.new_fetcher.assert_called_once()
        mock_page.goto.assert_called()
        mock_bm.close_fetcher.assert_called_once_with(mock_fetcher)

@pytest.mark.asyncio
async def test_get_post_detail_uses_browser_manager():
    crawler = PlaywrightYouTubeCrawler()
    with patch("app.crawlers.youtube.playwright_crawler.browser_manager") as mock_bm:
        mock_page = AsyncMock()
        mock_fetcher = FakeFetcher(mock_page)
        mock_bm.new_fetcher = AsyncMock(return_value=mock_fetcher)
        mock_bm.close_fetcher = AsyncMock()

        # Mock ytInitialData for video detail
        mock_page.evaluate.return_value = {
            "contents": {"twoColumnWatchNextResults": {"results": {"results": {"contents": []}}}},
            "currentVideoEndpoint": {"watchEndpoint": {"videoId": "vid123"}}
        }

        await crawler.get_post_detail("https://www.youtube.com/watch?v=vid123")

        mock_bm.new_fetcher.assert_called_once()
        mock_page.goto.assert_called()
        mock_bm.close_fetcher.assert_called_once_with(mock_fetcher)
