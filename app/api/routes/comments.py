"""
Comments API routes — list by post.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.comment_repo import CommentRepository
from app.schemas.comment import CommentCreate, CommentOut

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.post("", response_model=CommentOut, status_code=201)
async def create_comment(data: CommentCreate, db: AsyncSession = Depends(get_db)):
    repo = CommentRepository(db)
    return await repo.create_or_update(data)


@router.get("/by-post/{post_id}", response_model=dict)
async def list_comments_by_post(
    post_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    repo = CommentRepository(db)
    offset = (page - 1) * page_size
    items, total = await repo.list_by_post(post_id, limit=page_size, offset=offset)
    return {
        "items": [CommentOut.model_validate(c) for c in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
