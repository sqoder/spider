"""
Crawl API routes — trigger crawler tasks directly.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate, TaskOut
from app.workers.crawler_worker import execute_crawl_task

router = APIRouter(prefix="/crawl", tags=["Crawl"])


@router.post("/search", response_model=TaskOut)
async def crawl_search(
    platform: str,
    keyword: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a search crawl task.
    Delegates to CrawlService to create a Task and dispatch to Celery.
    """
    from app.services.crawl_service import CrawlService
    service = CrawlService(db)
    task = await service.trigger_search_crawl(platform, keyword, limit)
    return task
