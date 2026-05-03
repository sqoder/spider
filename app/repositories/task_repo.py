"""
CrawlTask repository — CRUD operations for the crawl_tasks table.
"""

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import CrawlTask
from app.schemas.task import TaskCreate


class TaskRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: TaskCreate) -> CrawlTask:
        task = CrawlTask(**data.model_dump())
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_by_id(self, task_id: int) -> CrawlTask | None:
        return await self.db.get(CrawlTask, task_id)

    async def list_tasks(
        self,
        platform: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[CrawlTask], int]:
        query = select(CrawlTask)
        count_query = select(func.count(CrawlTask.id))

        if platform:
            query = query.where(CrawlTask.platform == platform)
            count_query = count_query.where(CrawlTask.platform == platform)
        if status:
            query = query.where(CrawlTask.status == status)
            count_query = count_query.where(CrawlTask.status == status)

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(CrawlTask.id.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def mark_running(self, task_id: int) -> CrawlTask | None:
        task = await self.db.get(CrawlTask, task_id)
        if not task:
            return None
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_success(self, task_id: int, success_count: int) -> CrawlTask | None:
        task = await self.db.get(CrawlTask, task_id)
        if not task:
            return None
        task.status = "success"
        task.success_count = success_count
        task.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_failed(self, task_id: int, error_message: str, failed_count: int = 0) -> CrawlTask | None:
        task = await self.db.get(CrawlTask, task_id)
        if not task:
            return None
        task.status = "failed"
        task.error_message = error_message
        task.failed_count = failed_count
        task.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_partial(self, task_id: int, success_count: int, failed_count: int, error_message: str | None = None) -> CrawlTask | None:
        task = await self.db.get(CrawlTask, task_id)
        if not task:
            return None
        task.status = "partial_success"
        task.success_count = success_count
        task.failed_count = failed_count
        task.error_message = error_message
        task.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def set_celery_id(self, task_id: int, celery_task_id: str) -> None:
        task = await self.db.get(CrawlTask, task_id)
        if task:
            task.celery_task_id = celery_task_id
            await self.db.commit()
