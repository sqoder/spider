"""
Tests for API endpoints.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.crawlers.base import CrawlResult


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Test the health check endpoint."""

    async def test_health_check(self, client: AsyncClient):
        response = await client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "version" in data["data"]
        assert "supported_platforms" in data["data"]

    async def test_health_returns_platforms(self, client: AsyncClient):
        response = await client.get("/api/health")
        data = response.json()

        platforms = data["data"]["supported_platforms"]
        assert isinstance(platforms, list)


@pytest.mark.asyncio
class TestCrawlEndpoints:
    """Test direct crawl endpoints (uses same CrawlerFactory pattern as run.py)."""

    async def test_search_missing_keyword(self, client: AsyncClient):
        response = await client.post("/api/crawl/search", json={"platform": "youtube"})
        assert response.status_code == 422

    async def test_search_valid(self, client: AsyncClient):
        with patch("app.api.routes.crawl.CrawlerFactory.create") as mock_create:
            mock_crawler = AsyncMock()
            mock_result = CrawlResult(
                platform="youtube",
                source_id="test123",
                title="Test Video",
                url="https://youtube.com/watch?v=test123",
            )
            mock_crawler.search = AsyncMock(return_value=[mock_result])
            mock_crawler.close = AsyncMock()
            mock_create.return_value = mock_crawler

            response = await client.post(
                "/api/crawl/search",
                json={"platform": "youtube", "keyword": "AI", "limit": 10}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["platform"] == "youtube"
            assert data["keyword"] == "AI"

    async def test_detail_passes_comments_limit(self, client: AsyncClient):
        with patch("app.api.routes.crawl.CrawlerFactory.create") as mock_create:
            mock_crawler = AsyncMock()
            mock_result = CrawlResult(
                platform="youtube",
                source_id="vid12345678",
                title="Test",
                url="https://youtube.com/watch?v=vid12345678",
            )
            mock_crawler.get_post_detail = AsyncMock(return_value=mock_result)
            mock_crawler.get_comments = AsyncMock(return_value=[])
            mock_crawler.close = AsyncMock()
            mock_create.return_value = mock_crawler

            response = await client.post(
                "/api/crawl/detail",
                json={
                    "platform": "youtube",
                    "url": "https://www.youtube.com/watch?v=vid12345678",
                    "comments_limit": 123,
                },
            )
            assert response.status_code == 200
            mock_crawler.get_comments.assert_awaited_with("vid12345678", limit=123)


@pytest.mark.asyncio
class TestPostsEndpoints:
    """Test posts listing endpoints."""

    async def test_list_posts(self, client: AsyncClient):
        response = await client.get("/api/posts")
        assert response.status_code == 200

    async def test_get_post_not_found(self, client: AsyncClient):
        response = await client.get("/api/posts/99999")
        assert response.status_code == 404
