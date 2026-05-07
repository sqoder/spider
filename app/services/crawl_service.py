from dataclasses import dataclass
from typing import Callable

from loguru import logger

from app.crawlers.base import BaseCrawler
from app.crawlers.factory import CrawlerFactory
from app.storage.base_store import BaseStore
from app.storage.factory import StoreFactory
from app.services.media_service import MediaService


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
        media_service: MediaService | None = None,
    ):
        self._crawler_factory = crawler_factory or CrawlerFactory.create
        self._store_factory = store_factory or StoreFactory.create_store
        self._media_service = media_service or MediaService()

    async def search(
        self, platform: str, keyword: str, limit: int = 20, download_media: bool = False
    ) -> CrawlSearchResponse:
        crawler = self._crawler_factory(platform)
        try:
            results = await crawler.search(keyword, limit=limit)
            result_dicts = [result.to_dict() for result in results]

            store = self._store_factory(platform, "search")
            try:
                await store.store_content(result_dicts)
            finally:
                await store.close()

            if download_media:
                for item in results:
                    try:
                        await self._download_platform_media(
                            platform, item.url, item.source_id, item.to_dict()
                        )
                    except Exception as e:
                        logger.warning(f"Failed to download media for {item.url}: {e}")

            return CrawlSearchResponse(
                platform=platform,
                keyword=keyword,
                count=len(result_dicts),
                items=result_dicts,
            )
        finally:
            await crawler.close()

    async def detail(
        self, platform: str, url: str, comments_limit: int = 0, download_media: bool = False
    ) -> CrawlDetailResponse:
        crawler = self._crawler_factory(platform)
        try:
            result = await crawler.get_post_detail(url)
            result_dict = result.to_dict()

            comments = []
            if comments_limit > 0:
                try:
                    # Some crawlers might need extra context for comments (like reddit needing subreddit)
                    # But for now we follow the existing pattern in CrawlService
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

            if download_media:
                try:
                    await self._download_platform_media(
                        platform, url, result.source_id, result_dict
                    )
                except Exception as e:
                    logger.warning(f"Failed to download media for {url}: {e}")

            return CrawlDetailResponse(
                platform=platform,
                data=result_dict,
                comments=comment_dicts,
            )
        finally:
            await crawler.close()

    async def _download_platform_media(
        self, platform: str, url: str, source_id: str, data: dict
    ) -> None:
        if platform == "youtube":
            await self._media_service.download_youtube(url, source_id)
        elif platform == "tiktok":
            await self._media_service.download_tiktok(url, source_id)
        elif platform == "x":
            await self._media_service.download_x(url, source_id)
        elif platform == "instagram":
            await self._media_service.download_instagram(data.get("media", []), source_id)
        elif platform == "reddit":
            await self._media_service.download_reddit(
                data.get("media", []), source_id, post_url=url
            )
        else:
            logger.info(f"Media download not supported for platform: {platform}")
