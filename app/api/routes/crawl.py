"""
Crawl API routes — direct crawler pattern (same as run.py).
No Redis, no Celery, no DB — just CrawlerFactory + StoreFactory.
"""

from fastapi import APIRouter
from loguru import logger

from app.crawlers.factory import CrawlerFactory
from app.storage.factory import StoreFactory
from app.schemas.crawl import SearchRequest, DetailRequest

router = APIRouter(prefix="/crawl", tags=["Crawl"])


@router.post("/search")
async def crawl_search(request: SearchRequest):
    platform = request.platform.value if hasattr(request.platform, "value") else request.platform
    crawler = CrawlerFactory.create(platform)
    try:
        results = await crawler.search(request.keyword, limit=request.limit)
        results_dicts = [r.to_dict() for r in results]

        store = StoreFactory.create_store(platform, "search")
        try:
            await store.store_content(results_dicts)
        finally:
            await store.close()

        return {
            "platform": platform,
            "keyword": request.keyword,
            "count": len(results),
            "items": results_dicts,
        }
    finally:
        await crawler.close()


@router.post("/detail")
async def crawl_detail(request: DetailRequest):
    platform = request.platform.value if hasattr(request.platform, "value") else request.platform
    crawler = CrawlerFactory.create(platform)
    try:
        result = await crawler.get_post_detail(request.url)
        result_dict = result.to_dict()

        comments = []
        comment_dicts = []
        if request.comments_limit > 0:
            try:
                comments = await crawler.get_comments(
                    result.source_id, limit=request.comments_limit
                )
            except Exception as e:
                logger.warning(f"Failed to fetch comments for {result.source_id}: {e}")
        comment_dicts = [c.to_dict() for c in comments]

        store = StoreFactory.create_store(platform, "detail")
        try:
            await store.store_content([result_dict])
            if comment_dicts:
                await store.store_comment(result.source_id, comment_dicts)
        finally:
            await store.close()

        return {
            "platform": platform,
            "data": result_dict,
            "comments": comment_dicts,
        }
    finally:
        await crawler.close()
