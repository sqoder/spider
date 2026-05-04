"""
Tests for the base crawler and factory pattern.
"""

import pytest

from app.core.exceptions import PlatformNotSupportedError
from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.factory import CrawlerFactory

# ---- CrawlResult Tests ----


class TestCrawlResult:
    """Test the unified CrawlResult dataclass."""

    def test_to_dict_basic(self):
        result = CrawlResult(
            platform="youtube",
            source_id="abc123",
            url="https://youtube.com/watch?v=abc123",
            title="Test Video",
            content="Test description",
        )
        data = result.to_dict()

        assert data["platform"] == "youtube"
        assert data["source_id"] == "abc123"
        assert data["url"] == "https://youtube.com/watch?v=abc123"
        assert data["title"] == "Test Video"
        assert data["content"] == "Test description"
        assert data["metrics"]["like_count"] == 0
        assert data["metrics"]["view_count"] == 0
        assert data["media"] == []
        assert data["raw"] == {}

    def test_to_dict_with_metrics(self):
        result = CrawlResult(
            platform="reddit",
            source_id="xyz789",
            like_count=100,
            comment_count=50,
            share_count=10,
            view_count=5000,
        )
        data = result.to_dict()

        assert data["metrics"]["like_count"] == 100
        assert data["metrics"]["comment_count"] == 50
        assert data["metrics"]["share_count"] == 10
        assert data["metrics"]["view_count"] == 5000

    def test_to_dict_with_author(self):
        result = CrawlResult(
            platform="tiktok",
            source_id="vid001",
            author_id="user123",
            author_name="Test User",
            author_username="testuser",
            author_url="https://tiktok.com/@testuser",
        )
        data = result.to_dict()

        assert data["author"]["id"] == "user123"
        assert data["author"]["name"] == "Test User"
        assert data["author"]["username"] == "testuser"
        assert data["author"]["url"] == "https://tiktok.com/@testuser"

    def test_to_dict_with_media(self):
        result = CrawlResult(
            platform="youtube",
            source_id="abc123",
            media=[
                {"type": "video", "url": "https://example.com/video.mp4"},
                {"type": "image", "url": "https://example.com/thumb.jpg"},
            ],
        )
        data = result.to_dict()

        assert len(data["media"]) == 2
        assert data["media"][0]["type"] == "video"
        assert data["media"][1]["type"] == "image"

    def test_to_dict_preserves_visible_contract_metadata(self):
        result = CrawlResult(
            platform="youtube",
            source_id="abc123",
            visible_data={"title": "Visible title"},
            raw_sources={"yt_initial_data": {"ok": True}},
            capture_meta={"method": "visible_playwright"},
        )

        data = result.to_dict()

        assert data["visible_data"]["title"] == "Visible title"
        assert data["raw_sources"]["yt_initial_data"]["ok"] is True
        assert data["capture_meta"]["method"] == "visible_playwright"


class TestCommentResult:
    """Test the CommentResult dataclass."""

    def test_creation(self):
        comment = CommentResult(
            platform="youtube",
            source_id="comment001",
            content="Great video!",
            author_name="Commenter",
            like_count=5,
        )
        assert comment.platform == "youtube"
        assert comment.content == "Great video!"
        assert comment.like_count == 5
        assert comment.parent_comment_id is None

    def test_to_dict_preserves_visible_contract_metadata(self):
        comment = CommentResult(
            platform="youtube",
            source_id="comment001",
            content="Visible comment",
            visible_data={"content_text": "Visible comment", "thread_position": 1},
            raw_sources={"innertube": {"commentId": "comment001"}},
            capture_meta={"method": "innertube_comments"},
        )

        data = comment.to_dict()

        assert data["visible_data"]["thread_position"] == 1
        assert data["raw_sources"]["innertube"]["commentId"] == "comment001"
        assert data["capture_meta"]["method"] == "innertube_comments"


# ---- CrawlerFactory Tests ----


class TestCrawlerFactory:
    """Test the crawler factory pattern."""

    def test_unsupported_platform_raises_error(self):
        with pytest.raises(PlatformNotSupportedError):
            CrawlerFactory.create("nonexistent_platform")

    def test_get_supported_platforms(self):
        platforms = CrawlerFactory.get_supported_platforms()
        assert isinstance(platforms, list)

    def test_is_supported(self):
        # Should not support a random platform
        assert CrawlerFactory.is_supported("random_xyz") is False

    def test_register_and_create(self):
        """Test registering a mock crawler."""

        class MockCrawler(BaseCrawler):
            platform = "mock"

            async def search(self, keyword, limit=20):
                return []

            async def get_user_posts(self, username, limit=20):
                return []

            async def get_post_detail(self, url):
                return CrawlResult(platform="mock", source_id="1")

            async def get_comments(self, post_id, limit=50):
                return []

        CrawlerFactory.register("mock", MockCrawler)
        assert CrawlerFactory.is_supported("mock")

        crawler = CrawlerFactory.create("mock")
        assert isinstance(crawler, MockCrawler)
        assert crawler.platform == "mock"

        # Cleanup
        del CrawlerFactory._registry["mock"]
