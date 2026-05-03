"""
Authors API routes — CRUD + listing.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.author_repo import AuthorRepository
from app.schemas.author import AuthorCreate, AuthorOut, AuthorUpdate

router = APIRouter(prefix="/authors", tags=["Authors"])


@router.post("", response_model=AuthorOut, status_code=201)
async def create_author(data: AuthorCreate, db: AsyncSession = Depends(get_db)):
    """Create or update an author (upsert by platform + source_id)."""
    repo = AuthorRepository(db)
    return await repo.create_or_update(data)


@router.get("", response_model=dict)
async def list_authors(
    platform: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    repo = AuthorRepository(db)
    offset = (page - 1) * page_size
    items, total = await repo.list_authors(
        platform=platform, limit=page_size, offset=offset
    )
    return {
        "items": [AuthorOut.model_validate(a) for a in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{author_id}", response_model=AuthorOut)
async def get_author(author_id: int, db: AsyncSession = Depends(get_db)):
    repo = AuthorRepository(db)
    author = await repo.get_by_id(author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return author


@router.patch("/{author_id}", response_model=AuthorOut)
async def update_author(
    author_id: int, data: AuthorUpdate, db: AsyncSession = Depends(get_db)
):
    repo = AuthorRepository(db)
    author = await repo.update(author_id, data)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return author


@router.delete("/{author_id}", status_code=204)
async def delete_author(author_id: int, db: AsyncSession = Depends(get_db)):
    repo = AuthorRepository(db)
    deleted = await repo.delete(author_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Author not found")
