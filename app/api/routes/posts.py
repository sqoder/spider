"""
Posts API routes — CRUD + listing.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.post_repo import PostRepository
from app.schemas.post import PostCreate, PostListOut, PostOut, PostUpdate

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.post("", response_model=PostOut, status_code=201)
async def create_post(data: PostCreate, db: AsyncSession = Depends(get_db)):
    """
    Create or update a post (upsert by platform + source_id).
    If the same post already exists, its fields are updated.
    """
    repo = PostRepository(db)
    return await repo.create_or_update(data)


@router.get("", response_model=PostListOut)
async def list_posts(
    platform: str | None = Query(None, description="Filter by platform"),
    post_type: str | None = Query(None, description="Filter by post type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List posts with optional platform / type filter and pagination."""
    repo = PostRepository(db)
    offset = (page - 1) * page_size
    items, total = await repo.list_posts(
        platform=platform, post_type=post_type, limit=page_size, offset=offset
    )
    return PostListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single post by database ID."""
    repo = PostRepository(db)
    post = await repo.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int, data: PostUpdate, db: AsyncSession = Depends(get_db)
):
    """Partially update a post."""
    repo = PostRepository(db)
    post = await repo.update(post_id, data)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.delete("/{post_id}", status_code=204)
async def delete_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a post and its associated comments / media."""
    repo = PostRepository(db)
    deleted = await repo.delete(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
