"""
PostgreSQL storage operations.
Provides CRUD methods for posts, authors, comments, and tasks.
"""

from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.base import CommentResult, CrawlResult
from app.models.author import Author
from app.models.comment import Comment
from app.models.post import Post
from app.models.task import CrawlTask, TaskStatus


class PostgresStorage:
    """Database operations for the crawler system."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- Author Operations ----

    async def upsert_author(self, result: CrawlResult) -> Optional[Author]:
        """Create or update an author from crawl result data."""
        if not result.author_id:
            return None

        stmt = select(Author).where(
            and_(
                Author.platform == result.platform,
                Author.platform_id == result.author_id,
            )
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.display_name = result.author_name or existing.display_name
            existing.username = result.author_username or existing.username
            existing.profile_url = result.author_url or existing.profile_url
            existing.avatar_url = result.author_avatar or existing.avatar_url
            return existing

        author = Author(
            platform=result.platform,
            platform_id=result.author_id,
            username=result.author_username,
            display_name=result.author_name,
            profile_url=result.author_url,
            avatar_url=result.author_avatar,
        )
        self.session.add(author)
        await self.session.flush()
        return author

    # ---- Post Operations ----

    async def upsert_post(self, result: CrawlResult, task_id: Optional[int] = None) -> Post:
        """Create or update a post from crawl result data."""
        # Upsert author first
        author = await self.upsert_author(result)

        stmt = select(Post).where(
            and_(
                Post.platform == result.platform,
                Post.source_id == result.source_id,
            )
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.title = result.title or existing.title
            existing.content = result.content or existing.content
            existing.like_count = result.like_count
            existing.comment_count = result.comment_count
            existing.share_count = result.share_count
            existing.view_count = result.view_count
            existing.media = result.media or existing.media
            existing.raw_data = result.raw or existing.raw_data
            if author:
                existing.author_id = author.id
            return existing

        post = Post(
            platform=result.platform,
            source_id=result.source_id,
            url=result.url,
            title=result.title,
            content=result.content,
            content_type=result.content_type,
            author_id=author.id if author else None,
            like_count=result.like_count,
            comment_count=result.comment_count,
            share_count=result.share_count,
            view_count=result.view_count,
            media=result.media,
            thumbnail_url=result.thumbnail_url,
            published_at=result.published_at,
            raw_data=result.raw,
            crawl_task_id=task_id,
        )
        self.session.add(post)
        await self.session.flush()
        logger.debug(f"Saved post: {result.platform}/{result.source_id}")
        return post

    async def save_crawl_results(
        self, results: list[CrawlResult], task_id: Optional[int] = None
    ) -> list[Post]:
        """Save multiple crawl results to the database."""
        posts = []
        for result in results:
            try:
                post = await self.upsert_post(result, task_id=task_id)
                posts.append(post)
            except Exception as e:
                logger.error(f"Failed to save post {result.source_id}: {e}")
                continue

        await self.session.commit()
        logger.info(f"Saved {len(posts)} posts to database")
        return posts

    async def get_post(self, post_id: int) -> Optional[Post]:
        """Get a post by database ID."""
        return await self.session.get(Post, post_id)

    async def get_post_by_source(self, platform: str, source_id: str) -> Optional[Post]:
        """Get a post by platform and source ID."""
        stmt = select(Post).where(
            and_(Post.platform == platform, Post.source_id == source_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_posts(
        self,
        platform: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Post], int]:
        """List posts with optional platform filter and pagination."""
        query = select(Post)
        count_query = select(func.count(Post.id))

        if platform:
            query = query.where(Post.platform == platform)
            count_query = count_query.where(Post.platform == platform)

        # Get total count
        total = (await self.session.execute(count_query)).scalar() or 0

        # Get paginated results
        query = query.order_by(Post.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)

        return list(result.scalars().all()), total

    # ---- Comment Operations ----

    async def save_comments(
        self, comments: list[CommentResult], post_id: int
    ) -> list[Comment]:
        """Save comments for a post."""
        saved = []
        for comment_data in comments:
            try:
                stmt = select(Comment).where(
                    and_(
                        Comment.platform == comment_data.platform,
                        Comment.source_id == comment_data.source_id,
                    )
                )
                existing = (await self.session.execute(stmt)).scalar_one_or_none()

                if existing:
                    existing.content = comment_data.content
                    existing.like_count = comment_data.like_count
                    saved.append(existing)
                    continue

                comment = Comment(
                    platform=comment_data.platform,
                    source_id=comment_data.source_id,
                    post_id=post_id,
                    content=comment_data.content,
                    author_name=comment_data.author_name,
                    author_username=comment_data.author_username,
                    author_id=comment_data.author_id,
                    like_count=comment_data.like_count,
                    reply_count=comment_data.reply_count,
                    parent_comment_id=comment_data.parent_comment_id,
                    published_at=comment_data.published_at,
                    raw_data=comment_data.raw,
                )
                self.session.add(comment)
                saved.append(comment)
            except Exception as e:
                logger.error(f"Failed to save comment {comment_data.source_id}: {e}")

        await self.session.flush()
        return saved

    # ---- Task Operations ----

    async def create_task(self, **kwargs) -> CrawlTask:
        """Create a new crawl task."""
        task = CrawlTask(**kwargs)
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_task(self, task_id: int) -> Optional[CrawlTask]:
        """Get a task by ID."""
        return await self.session.get(CrawlTask, task_id)

    async def update_task_status(
        self,
        task_id: int,
        status: str,
        error_message: Optional[str] = None,
        result_count: Optional[int] = None,
    ) -> Optional[CrawlTask]:
        """Update task status."""
        task = await self.session.get(CrawlTask, task_id)
        if not task:
            return None

        task.status = status
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.utcnow()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.completed_at = datetime.utcnow()

        if error_message:
            task.error_message = error_message
        if result_count is not None:
            task.result_count = result_count

        await self.session.flush()
        return task

    async def list_tasks(
        self,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CrawlTask], int]:
        """List tasks with optional filters."""
        query = select(CrawlTask)
        count_query = select(func.count(CrawlTask.id))

        if status:
            query = query.where(CrawlTask.status == status)
            count_query = count_query.where(CrawlTask.status == status)
        if platform:
            query = query.where(CrawlTask.platform == platform)
            count_query = count_query.where(CrawlTask.platform == platform)

        total = (await self.session.execute(count_query)).scalar() or 0

        query = query.order_by(CrawlTask.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)

        return list(result.scalars().all()), total
