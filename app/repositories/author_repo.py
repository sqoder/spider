"""
Author repository — CRUD operations for the authors table.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.author import Author
from app.schemas.author import AuthorCreate, AuthorUpdate


class AuthorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update(self, data: AuthorCreate) -> Author:
        """Upsert: create if new, update if platform+source_id exists."""
        stmt = select(Author).where(
            Author.platform == data.platform,
            Author.source_id == data.source_id,
        )
        result = await self.db.execute(stmt)
        author = result.scalar_one_or_none()

        if author:
            # Update existing — only overwrite non-None fields
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if value is not None:
                    setattr(author, key, value)
        else:
            author = Author(**data.model_dump())
            self.db.add(author)

        await self.db.commit()
        await self.db.refresh(author)
        return author

    async def bulk_create_or_update(self, items: list[AuthorCreate]) -> list[Author]:
        """Upsert multiple authors using a single query per platform and a single commit."""
        if not items:
            return []

        platform_ids = {}
        for item in items:
            platform_ids.setdefault(item.platform, []).append(item.source_id)

        existing_authors = {}
        for platform, source_ids in platform_ids.items():
            stmt = select(Author).where(Author.platform == platform, Author.source_id.in_(source_ids))
            result = await self.db.execute(stmt)
            for a in result.scalars().all():
                existing_authors[(a.platform, a.source_id)] = a

        results = []
        new_authors = []
        for item in items:
            key = (item.platform, item.source_id)
            if key in existing_authors:
                author = existing_authors[key]
                update_data = item.model_dump(exclude_unset=True)
                for k, v in update_data.items():
                    if v is not None:
                        setattr(author, k, v)
                results.append(author)
            else:
                author = Author(**item.model_dump())
                new_authors.append(author)
                results.append(author)
                existing_authors[key] = author

        if new_authors:
            self.db.add_all(new_authors)
            
        await self.db.commit()
        return results

    async def get_by_id(self, author_id: int) -> Author | None:
        return await self.db.get(Author, author_id)

    async def get_by_platform_id(self, platform: str, source_id: str) -> Author | None:
        stmt = select(Author).where(
            Author.platform == platform,
            Author.source_id == source_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_authors(
        self,
        platform: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Author], int]:
        """Paginated list with optional platform filter. Returns (items, total)."""
        query = select(Author)
        count_query = select(func.count(Author.id))

        if platform:
            query = query.where(Author.platform == platform)
            count_query = count_query.where(Author.platform == platform)

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Author.id.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def update(self, author_id: int, data: AuthorUpdate) -> Author | None:
        author = await self.db.get(Author, author_id)
        if not author:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(author, key, value)

        await self.db.commit()
        await self.db.refresh(author)
        return author

    async def delete(self, author_id: int) -> bool:
        author = await self.db.get(Author, author_id)
        if not author:
            return False
        await self.db.delete(author)
        await self.db.commit()
        return True
