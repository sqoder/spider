"""
Database-based store implementation (PostgreSQL, SQLite).
Uses existing repositories to ensure deduplication and consistency.
"""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.repositories.author_repo import AuthorRepository
from app.repositories.comment_repo import CommentRepository
from app.repositories.post_repo import PostRepository
from app.schemas.author import AuthorCreate
from app.schemas.comment import CommentCreate
from app.schemas.post import PostCreate
from app.storage.base_store import BaseStore


class DbStoreImplement(BaseStore):
    """Implementation for database storage."""

    def __init__(self, platform: str, crawler_type: str):
        super().__init__(platform, crawler_type)
        self.session_factory = get_session_factory()
        self._session: AsyncSession | None = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = self.session_factory()
        return self._session

    async def store_content(self, items: list[dict]):
        session = await self._get_session()
        post_repo = PostRepository(session)
        author_repo = AuthorRepository(session)

        for item in items:
            try:
                # Handle Author first if present
                author_id = None
                author_data_raw = item.get("author")
                if isinstance(author_data_raw, dict):
                    author_source_id = author_data_raw.get("id") or author_data_raw.get("source_id")
                    if not author_source_id:
                        author_data_raw = None
                if isinstance(author_data_raw, dict):
                    visible = item.get("visible_data") or {}
                    author_schema = AuthorCreate(
                        platform=self.platform,
                        source_id=author_source_id,
                        username=author_data_raw.get("username"),
                        display_name=author_data_raw.get("name"),
                        profile_url=author_data_raw.get("url"),
                        avatar_url=author_data_raw.get("avatar"),
                        visible_data=self._author_visible_data(visible),
                    )
                    author = await author_repo.create_or_update(author_schema)
                    author_id = author.id

                # Handle Post
                post_schema = PostCreate(
                    platform=self.platform,
                    source_id=item.get("source_id") or item.get("id"),
                    author_id=author_id,
                    url=item.get("url"),
                    title=item.get("title"),
                    content=item.get("content") or item.get("description"),
                    post_type=item.get("content_type") or "video",
                    published_at=item.get("published_at"),
                    like_count=item.get("metrics", {}).get("like_count", 0),
                    comment_count=item.get("metrics", {}).get("comment_count", 0),
                    share_count=item.get("metrics", {}).get("share_count", 0),
                    view_count=item.get("metrics", {}).get("view_count", 0),
                    raw_data=item,
                    visible_data=item.get("visible_data"),
                    raw_sources=item.get("raw_sources"),
                    capture_meta=item.get("capture_meta"),
                )
                await post_repo.create_or_update(post_schema)
            except Exception as e:
                logger.error(f"Failed to store content in DB: {e}")

        await session.commit()

    async def store_comment(self, post_id: str, items: list[dict]):
        session = await self._get_session()
        comment_repo = CommentRepository(session)
        post_repo = PostRepository(session)

        # We need the internal DB post ID
        db_post = await post_repo.get_by_source_id(self.platform, post_id)
        if not db_post:
            logger.warning(f"Post {post_id} not found in DB. Skipping comments.")
            return

        for item in items:
            try:
                comment_schema = CommentCreate(
                    platform=self.platform,
                    source_id=item.get("source_id") or item.get("id") or item.get("comment_id"),
                    post_id=db_post.id,
                    author_name=item.get("author") or item.get("author_name"),
                    author_source_id=item.get("author_id") or item.get("author_source_id"),
                    content=item.get("text") or item.get("content"),
                    like_count=item.get("like_count") or 0,
                    reply_count=item.get("reply_count") or 0,
                    parent_comment_id=item.get("parent_id") or item.get("parent_comment_id"),
                    published_at=item.get("published_at") or item.get("timestamp"),
                    raw_data=item,
                    visible_data=item.get("visible_data"),
                    raw_sources=item.get("raw_sources"),
                    capture_meta=item.get("capture_meta"),
                )
                await comment_repo.create_or_update(comment_schema)
            except Exception as e:
                logger.error(f"Failed to store comment in DB: {e}")

        await session.commit()

    async def store_creator(self, items: list[dict]):
        session = await self._get_session()
        author_repo = AuthorRepository(session)

        for item in items:
            try:
                source_id = item.get("id") or item.get("source_id") or item.get("user_id")
                if not source_id:
                    continue
                author_schema = AuthorCreate(
                    platform=self.platform,
                    source_id=source_id,
                    username=item.get("username"),
                    display_name=item.get("name") or item.get("nickname"),
                    profile_url=item.get("url"),
                    avatar_url=item.get("avatar"),
                    bio=item.get("description") or item.get("desc"),
                    visible_data=item.get("visible_data"),
                )
                await author_repo.create_or_update(author_schema)
            except Exception as e:
                logger.error(f"Failed to store creator in DB: {e}")

        await session.commit()

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    @staticmethod
    def _author_visible_data(visible: dict) -> dict | None:
        if not visible:
            return None

        keys = {
            "channel_name",
            "channel_handle",
            "channel_url",
            "channel_avatar",
            "channel_verified",
            "subscriber_count_text",
            "subscriber_count",
        }
        data = {key: visible.get(key) for key in keys if visible.get(key) is not None}
        return data or None
