"""
Crawl Service Layer
Handles business logic for creating and managing crawl tasks.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate
from app.workers.crawler_worker import execute_crawl_task

class CrawlService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_repo = TaskRepository(db)

    async def trigger_search_crawl(
        self, platform: str, keyword: str, limit: int = 20
    ) -> dict:
        """
        Creates a Task record and dispatches it to Celery for background processing.
        """
        # Create the task
        task_data = TaskCreate(
            platform=platform,
            task_type="search",
            keyword=keyword,
            limit_count=limit,
        )
        task = await self.task_repo.create(task_data)
        
        # Dispatch to Celery
        celery_task = execute_crawl_task.delay(task.id)
        
        # Update celery_task_id
        await self.task_repo.set_celery_id(task.id, celery_task.id)
        await self.db.refresh(task)
        
        return task
