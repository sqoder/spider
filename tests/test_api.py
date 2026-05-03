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
class TestCrawlEndpoints:
    """Test direct crawl endpoints."""

    async def test_search_missing_keyword(self, client: AsyncClient):
        response = await client.post("/api/crawl/search?platform=youtube")
        # Should fail validation (keyword is required)
        assert response.status_code == 422

    async def test_create_task_valid(self, client: AsyncClient):
        from unittest.mock import patch

        with patch("app.api.routes.crawl.execute_crawl_task.delay") as mock_delay:
            mock_delay.return_value.id = "fake-celery-id"
            response = await client.post(
                "/api/crawl/search?platform=youtube&keyword=AI&limit=10"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["platform"] == "youtube"
            assert data["task_type"] == "search"
            assert data["keyword"] == "AI"


@pytest.mark.asyncio
class TestPostsEndpoints:
    """Test posts listing endpoints."""

    async def test_list_posts(self, client: AsyncClient):
        response = await client.get("/api/posts")
        assert response.status_code == 200

    async def test_get_post_not_found(self, client: AsyncClient):
        response = await client.get("/api/posts/99999")
        assert response.status_code == 404
