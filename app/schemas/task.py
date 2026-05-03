"""
Pydantic schemas for CrawlTask.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    platform: str
    task_type: str  # search | user_posts | post_detail | comments | url_parse
    keyword: str | None = None
    username: str | None = None
    url: str | None = None
    limit_count: int = Field(default=20, ge=1, le=200)
    params: dict | None = None


class TaskCreate(TaskBase):
    pass


class TaskOut(TaskBase):
    id: int
    status: str
    success_count: int = 0
    failed_count: int = 0
    error_message: str | None = None
    celery_task_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int = 1
    page_size: int = 20
