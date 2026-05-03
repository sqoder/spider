from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.factory import CrawlerFactory
from app.core.exceptions import PlatformNotSupportedError
from app.storage.redis import redis_storage
from app.repositories.post_repo import PostRepository
from app.schemas.post import PostCreate


class CrawlService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.post_repo = PostRepository(db)

    async def search(self, platform: str, keyword: str, limit: int = 20) -> dict:
        if not CrawlerFactory.is_supported(platform):
            raise PlatformNotSupportedError(platform)

        cache_key = f"search:{platform}:{keyword}:{limit}"
        cached = await redis_storage.cache_json_get(cache_key)

        if cached:
            return {
                "platform": platform,
                "keyword": keyword,
                "count": len(cached.get("items", [])),
                "items": cached.get("items", []),
                "cached": True,
            }

        crawler = CrawlerFactory.create(platform)

        try:
            results = await crawler.search(keyword, limit=limit)

            saved_items = []
            for item in results:
                data = self._crawl_result_to_post_create(platform, item)
                post = await self.post_repo.create_or_update(data)
                saved_items.append(post)

            response = {
                "platform": platform,
                "keyword": keyword,
                "count": len(results),
                "items": [item.to_dict() for item in results],
                "cached": False,
            }

            await redis_storage.cache_json_set(cache_key, response, ttl=1800)
            return response

        finally:
            try:
                await crawler.close()
            except Exception as exc:
                logger.warning(f"Failed to close crawler: {exc}")

    def _crawl_result_to_post_create(self, platform: str, item) -> PostCreate:
        data = item.to_dict()

        return PostCreate(
            platform=platform,
            source_id=str(data.get("source_id") or data.get("id")),
            url=data.get("url"),
            title=data.get("title"),
            content=data.get("content") or data.get("description"),
            post_type=data.get("post_type") or "video",
            published_at=data.get("published_at"),
            like_count=data.get("like_count") or 0,
            comment_count=data.get("comment_count") or 0,
            share_count=data.get("share_count") or 0,
            view_count=data.get("view_count") or 0,
            raw_data=data,
        )
