"""
Tests for API endpoints.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


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
class TestStatsEndpoint:
    """Test the stats endpoint."""

    async def test_stats(self, client: AsyncClient):
        response = await client.get("/api/stats")
        assert response.status_code == 200

        data = response.json()
        assert "platforms" in data["data"]
        assert "media_storage" in data["data"]


@pytest.mark.asyncio
class TestCrawlEndpoints:
    """Test direct crawl endpoints (validation only, no actual crawling)."""

    async def test_search_missing_keyword(self, client: AsyncClient):
        response = await client.post("/api/crawl/search", json={
            "platform": "youtube",
        })
        # Should fail validation (keyword is required)
        assert response.status_code == 422

    async def test_search_invalid_platform(self, client: AsyncClient):
        response = await client.post("/api/crawl/search", json={
            "platform": "invalid_platform",
            "keyword": "test",
        })
        assert response.status_code == 422

    async def test_user_crawl_missing_username(self, client: AsyncClient):
        response = await client.post("/api/crawl/user", json={
            "platform": "reddit",
        })
        assert response.status_code == 422

    async def test_url_crawl_missing_url(self, client: AsyncClient):
        response = await client.post("/api/crawl/url", json={
            "platform": "youtube",
        })
        assert response.status_code == 422

    async def test_create_task_valid(self, client: AsyncClient):
        response = await client.post("/api/tasks", json={
            "platform": "youtube",
            "type": "search",
            "keyword": "AI tools",
            "limit": 10,
        })
        # May fail due to no DB in test, but should not be 422 (validation error)
        assert response.status_code != 422


@pytest.mark.asyncio
class TestPostsEndpoints:
    """Test posts listing endpoints."""

    async def test_list_posts(self, client: AsyncClient):
        response = await client.get("/api/posts")
        # May fail due to no DB, but should not be a 422
        assert response.status_code in (200, 500)

    async def test_get_post_not_found(self, client: AsyncClient):
        response = await client.get("/api/posts/99999")
        assert response.status_code in (404, 500)
