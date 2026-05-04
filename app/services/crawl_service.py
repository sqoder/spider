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

    async def search(
        self, platform: str, keyword: str, limit: int = 20, deep: bool = False
    ) -> dict:
        if not CrawlerFactory.is_supported(platform):
            raise PlatformNotSupportedError(platform)

        cache_key = f"search:{platform}:{keyword}:{limit}:{deep}"
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
            results_dicts = [item.to_dict() for item in results]

            # Unified storage via factory
            from app.storage.factory import StoreFactory
            store = StoreFactory.create_store(platform, "search")
            try:
                await store.store_content(results_dicts)
            finally:
                await store.close()

            # Trigger deep crawl tasks if needed
            if deep:
                for item in results:
                    try:
                        from app.repositories.task_repo import TaskRepository
                        from app.schemas.task import TaskCreate
                        from app.workers.crawler_worker import execute_crawl_task
                        
                        task_repo = TaskRepository(self.db)
                        task_data = TaskCreate(
                            platform=platform,
                            task_type="post_detail",
                            url=item.url,
                            limit_count=200
                        )
                        new_task = await task_repo.create(task_data)
                        execute_crawl_task.delay(new_task.id)
                        import asyncio
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Failed to queue deep crawl for {item.url}: {e}")

            response = {
                "platform": platform,
                "keyword": keyword,
                "count": len(results),
                "items": results_dicts,
                "cached": False,
            }
            await redis_storage.cache_json_set(cache_key, response, ttl=1800)
            return response
        except Exception as e:
            logger.exception(f"Detailed error in search: {e}")
            raise
        finally:
            try:
                await crawler.close()
            except Exception as exc:
                logger.warning(f"Failed to close crawler: {exc}")

    async def get_detail(self, platform: str, url: str) -> dict:
        """Comprehensive no-blind-spot extraction for a specific post."""
        if not CrawlerFactory.is_supported(platform):
            raise PlatformNotSupportedError(platform)

        crawler = CrawlerFactory.create(platform)
        try:
            # 1. Fetch comprehensive text data
            result = await crawler.get_post_detail(url)
            result_dict = result.to_dict()
            
            # 2. Unified storage via factory
            from app.storage.factory import StoreFactory
            store = StoreFactory.create_store(platform, "detail")
            try:
                # Store main content
                await store.store_content([result_dict])
                
                # Store comments separately if present
                comments = result.raw.get("comments", [])
                if comments:
                    await store.store_comment(result.source_id, comments)
                
                # Store author/creator separately if present
                author_data = result_dict.get("author")
                if author_data:
                    await store.store_creator([author_data])
            finally:
                await store.close()

            # 3. Trigger async media download
            try:
                from app.workers.crawler_worker import download_media
                download_media.delay(platform, url, result.source_id)
                media_status = "Media downloading in background"
            except Exception as e:
                logger.error(f"Failed to queue media download: {e}")
                media_status = "Media download queue failed"
            
            return {
                "platform": platform,
                "source_id": result.source_id,
                "message": f"Comprehensive extraction successful. {media_status}",
                "data": result_dict
            }
        finally:
            try:
                await crawler.close()
            except Exception as exc:
                logger.warning(f"Failed to close crawler: {exc}")

    async def _save_crawl_result(self, platform: str, r) -> any:
        """Helper to save a CrawlResult (Post + Author) to the database."""
        from app.repositories.author_repo import AuthorRepository
        from app.schemas.author import AuthorCreate

        author_repo = AuthorRepository(self.db)
        author_id = None

        if r.author_id:
            author_data = AuthorCreate(
                platform=r.platform,
                source_id=r.author_id,
                username=r.author_username,
                display_name=r.author_name,
                profile_url=r.author_url,
                avatar_url=r.author_avatar,
            )
            author = await author_repo.create_or_update(author_data)
            author_id = author.id

        post_data = self._crawl_result_to_post_create(platform, r)
        post_data.author_id = author_id
        
        return await self.post_repo.create_or_update(post_data)

    def _crawl_result_to_post_create(self, platform: str, item) -> PostCreate:
        data = item.to_dict()

        return PostCreate(
            platform=platform,
            source_id=str(data.get("source_id") or data.get("id")),
            url=data.get("url"),
            title=data.get("title"),
            content=data.get("content") or data.get("description"),
            post_type=data.get("content_type") or "video",
            published_at=data.get("published_at"),
            like_count=data.get("like_count") or 0,
            comment_count=data.get("comment_count") or 0,
            share_count=data.get("share_count") or 0,
            view_count=data.get("view_count") or 0,
            raw_data=data,
        )
