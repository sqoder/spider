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
