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

    async def bulk_create(self, items: list[CommentCreate]) -> list[Comment]:
        results = []
        for data in items:
            comment = await self.create_or_update(data)
            results.append(comment)
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
