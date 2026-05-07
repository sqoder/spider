"""
Post repository — CRUD operations for the posts table.
Handles upsert (platform+source_id dedup), pagination, and filtering.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.post import Post
from app.schemas.post import PostCreate, PostUpdate


class PostRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update(self, data: PostCreate) -> Post:
        """
        Upsert a post by (platform, source_id).
        If the same post already exists, update it instead of creating a duplicate.
        """
        stmt = select(Post).where(
            Post.platform == data.platform,
            Post.source_id == data.source_id,
        )
        result = await self.db.execute(stmt)
        post = result.scalar_one_or_none()

        if post:
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if value is not None:
                    setattr(post, key, value)
        else:
            post = Post(**data.model_dump())
            self.db.add(post)

        await self.db.commit()
        await self.db.refresh(post)
        return post

    async def bulk_create_or_update(self, items: list[PostCreate], chunk_size: int = 500) -> list[Post]:
        """Upsert multiple posts in safe, optimized chunks to prevent DB bottlenecks."""
        if not items:
            return []

        results = []
        for i in range(0, len(items), chunk_size):
            chunk = items[i : i + chunk_size]
            chunk_results = await self._bulk_create_or_update_chunk(chunk)
            results.extend(chunk_results)
        return results

    async def _bulk_create_or_update_chunk(self, items: list[PostCreate]) -> list[Post]:
        """Upsert a single chunk of posts."""
        if not items:
            return []

        # 1. Group source_ids by platform
        platform_ids = {}
        for item in items:
            platform_ids.setdefault(item.platform, []).append(item.source_id)

        # 2. Fetch existing posts
        existing_posts = {}
        for platform, source_ids in platform_ids.items():
            stmt = select(Post).where(Post.platform == platform, Post.source_id.in_(source_ids))
            result = await self.db.execute(stmt)
            for p in result.scalars().all():
                existing_posts[(p.platform, p.source_id)] = p

        # 3. Update existing or create new
        results = []
        new_posts = []
        for item in items:
            key = (item.platform, item.source_id)
            if key in existing_posts:
                post = existing_posts[key]
                update_data = item.model_dump(exclude_unset=True)
                for k, v in update_data.items():
                    if v is not None:
                        setattr(post, k, v)
                results.append(post)
            else:
                post = Post(**item.model_dump())
                new_posts.append(post)
                results.append(post)
                existing_posts[key] = post  # prevent duplicates within the batch

        # 4. Save and commit
        if new_posts:
            self.db.add_all(new_posts)
            
        await self.db.commit()
        return results

    async def get_by_id(self, post_id: int) -> Post | None:
        return await self.db.get(Post, post_id)

    async def get_by_platform_id(self, platform: str, source_id: str) -> Post | None:
        stmt = select(Post).where(
            Post.platform == platform,
            Post.source_id == source_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_source_id(self, platform: str, source_id: str) -> Post | None:
        """Compatibility alias used by storage implementations."""
        return await self.get_by_platform_id(platform, source_id)

    async def list_posts(
        self,
        platform: str | None = None,
        post_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Post], int]:
        """Paginated list with optional filters. Returns (items, total)."""
        query = select(Post)
        count_query = select(func.count(Post.id))

        if platform:
            query = query.where(Post.platform == platform)
            count_query = count_query.where(Post.platform == platform)
        if post_type:
            query = query.where(Post.post_type == post_type)
            count_query = count_query.where(Post.post_type == post_type)

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Post.id.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def update(self, post_id: int, data: PostUpdate) -> Post | None:
        post = await self.db.get(Post, post_id)
        if not post:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(post, key, value)

        await self.db.commit()
        await self.db.refresh(post)
        return post

    async def delete(self, post_id: int) -> bool:
        post = await self.db.get(Post, post_id)
        if not post:
            return False
        await self.db.delete(post)
        await self.db.commit()
        return True
