"""
Tasks API routes — create crawl tasks + status tracking.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate, TaskListOut, TaskOut

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Create a new crawl task."""
    repo = TaskRepository(db)
    return await repo.create(data)


@router.get("", response_model=TaskListOut)
async def list_tasks(
    platform: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    repo = TaskRepository(db)
    offset = (page - 1) * page_size
    items, total = await repo.list_tasks(
        platform=platform, status=status, limit=page_size, offset=offset
    )
    return TaskListOut(items=items, total=total, page=page, page_size=page_size)  # type: ignore[arg-type]


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    repo = TaskRepository(db)
    task = await repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
