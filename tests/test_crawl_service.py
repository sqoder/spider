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
        crawler_factory=lambda platform: crawler,  # type: ignore[arg-type]
        store_factory=lambda platform, task_type: store,  # type: ignore[arg-type]
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
        crawler_factory=lambda platform: crawler,  # type: ignore[arg-type]
        store_factory=lambda platform, task_type: store,  # type: ignore[arg-type]
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
    assert store.closed is True
    assert crawler.closed is True
