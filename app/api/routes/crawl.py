"""
Crawl API routes — trigger crawler tasks directly.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.crawl import SearchRequest
from app.services.crawl_service import CrawlService

router = APIRouter(prefix="/crawl", tags=["Crawl"])

@router.post("/search")
async def crawl_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    service = CrawlService(db)
    return await service.search(
        platform=request.platform.value if hasattr(request.platform, "value") else request.platform,
        keyword=request.keyword,
        limit=request.limit,
    )
