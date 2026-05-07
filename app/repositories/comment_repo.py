"""
Comment repository — CRUD operations for the comments table.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.schemas.comment import CommentCreate


class CommentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update(self, data: CommentCreate) -> Comment:
        """Upsert by (platform, source_id)."""
        stmt = select(Comment).where(
            Comment.platform == data.platform,
            Comment.source_id == data.source_id,
        )
        result = await self.db.execute(stmt)
        comment = result.scalar_one_or_none()

        if comment:
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if value is not None:
                    setattr(comment, key, value)
        else:
            comment = Comment(**data.model_dump())
            self.db.add(comment)

        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def bulk_create(self, items: list[CommentCreate], chunk_size: int = 500) -> list[Comment]:
        """Upsert multiple comments in safe, optimized chunks to prevent DB bottlenecks."""
        if not items:
            return []

        results = []
        for i in range(0, len(items), chunk_size):
            chunk = items[i : i + chunk_size]
            chunk_results = await self._bulk_create_chunk(chunk)
            results.extend(chunk_results)
        return results

    async def _bulk_create_chunk(self, items: list[CommentCreate]) -> list[Comment]:
        """Upsert a single chunk of comments."""
        if not items:
            return []

        platform_ids = {}
        for item in items:
            platform_ids.setdefault(item.platform, []).append(item.source_id)

        existing_comments = {}
        for platform, source_ids in platform_ids.items():
            stmt = select(Comment).where(Comment.platform == platform, Comment.source_id.in_(source_ids))
            result = await self.db.execute(stmt)
            for c in result.scalars().all():
                existing_comments[(c.platform, c.source_id)] = c

        results = []
        new_comments = []
        for item in items:
            key = (item.platform, item.source_id)
            if key in existing_comments:
                comment = existing_comments[key]
                update_data = item.model_dump(exclude_unset=True)
                for k, v in update_data.items():
                    if v is not None:
                        setattr(comment, k, v)
                results.append(comment)
            else:
                comment = Comment(**item.model_dump())
                new_comments.append(comment)
                results.append(comment)
                existing_comments[key] = comment

        if new_comments:
            self.db.add_all(new_comments)
            
        await self.db.commit()
        return results

    async def get_by_id(self, comment_id: int) -> Comment | None:
        return await self.db.get(Comment, comment_id)

    async def list_by_post(
        self,
        post_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Comment], int]:
        count_query = select(func.count(Comment.id)).where(Comment.post_id == post_id)
        total = (await self.db.execute(count_query)).scalar() or 0

        query = (
            select(Comment)
            .where(Comment.post_id == post_id)
            .order_by(Comment.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def delete(self, comment_id: int) -> bool:
        comment = await self.db.get(Comment, comment_id)
        if not comment:
            return False
        await self.db.delete(comment)
        await self.db.commit()
        return True
