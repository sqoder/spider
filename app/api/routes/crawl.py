"""
Crawl API routes — direct crawler pattern (same as run.py).
No Redis, no Celery, no DB — just CrawlerFactory + StoreFactory.
"""

from fastapi import APIRouter

from app.services.crawl_service import CrawlService
from app.schemas.crawl import SearchRequest, DetailRequest

router = APIRouter(prefix="/crawl", tags=["Crawl"])


@router.post("/search")
async def crawl_search(request: SearchRequest):
    platform = request.platform.value if hasattr(request.platform, "value") else request.platform
    result = await CrawlService().search(platform, request.keyword, limit=request.limit)
    return {
        "platform": result.platform,
        "keyword": result.keyword,
        "count": result.count,
        "items": result.items,
    }


@router.post("/detail")
async def crawl_detail(request: DetailRequest):
    platform = request.platform.value if hasattr(request.platform, "value") else request.platform
    result = await CrawlService().detail(
        platform,
        request.url,
        comments_limit=request.comments_limit,
    )
    return {
        "platform": result.platform,
        "data": result.data,
        "comments": result.comments,
    }
