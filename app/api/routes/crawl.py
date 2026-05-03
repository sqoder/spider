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
    Creates a Task record and dispatches it to Celery.
    """
    repo = TaskRepository(db)
    
    # Create the task
    task_data = TaskCreate(
        platform=platform,
        task_type="search",
        keyword=keyword,
        limit_count=limit,
    )
    task = await repo.create(task_data)
    
    # Dispatch to Celery
    celery_task = execute_crawl_task.delay(task.id)
    
    # Update celery_task_id
    await repo.set_celery_id(task.id, celery_task.id)
    await db.refresh(task)
    
    return task
