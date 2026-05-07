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

        # 1. Gather all authors
        author_schemas = []
        author_map = {}  # local mapping to avoid creating duplicates in this batch
        
        for item in items:
            author_data_raw = item.get("author")
            if isinstance(author_data_raw, dict):
                author_source_id = author_data_raw.get("id") or author_data_raw.get("source_id")
                if author_source_id and author_source_id not in author_map:
                    visible = item.get("visible_data") or {}
                    author_schema = AuthorCreate(
                        platform=self.platform,
                        source_id=author_source_id,  # type: ignore[arg-type]
                        username=author_data_raw.get("username"),
                        display_name=author_data_raw.get("name"),
                        profile_url=author_data_raw.get("url"),
                        avatar_url=author_data_raw.get("avatar"),
                        visible_data=self._author_visible_data(visible),
                    )
                    author_schemas.append(author_schema)
                    author_map[author_source_id] = author_schema

        # 2. Bulk upsert authors
        saved_authors = {}
        if author_schemas:
            try:
                authors = await author_repo.bulk_create_or_update(author_schemas)
                for a in authors:
                    saved_authors[a.source_id] = a.id
            except Exception as e:
                logger.error(f"Failed to bulk store authors: {e}")

        # 3. Gather posts and map author_ids
        post_schemas = []
        for item in items:
            try:
                author_data_raw = item.get("author")
                author_id = None
                if isinstance(author_data_raw, dict):
                    author_source_id = author_data_raw.get("id") or author_data_raw.get("source_id")
                    author_id = saved_authors.get(author_source_id)

                post_schema = PostCreate(
                    platform=self.platform,
                    source_id=item.get("source_id") or item.get("id"),  # type: ignore[arg-type]
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
                post_schemas.append(post_schema)
            except Exception as e:
                logger.error(f"Failed to process content item for DB: {e}")
                
        # 4. Bulk upsert posts
        if post_schemas:
            try:
                await post_repo.bulk_create_or_update(post_schemas)
            except Exception as e:
                logger.error(f"Failed to bulk store posts in DB: {e}")

    async def store_comment(self, post_id: str, items: list[dict]):
        session = await self._get_session()
        comment_repo = CommentRepository(session)
        post_repo = PostRepository(session)

        # We need the internal DB post ID
        db_post = await post_repo.get_by_source_id(self.platform, post_id)
        if not db_post:
            logger.warning(f"Post {post_id} not found in DB. Skipping comments.")
            return

        comment_schemas = []
        for item in items:
            try:
                comment_schema = CommentCreate(
                    platform=self.platform,
                    source_id=item.get("source_id") or item.get("id") or item.get("comment_id"),  # type: ignore[arg-type]
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
                comment_schemas.append(comment_schema)
            except Exception as e:
                logger.error(f"Failed to process comment item for DB: {e}")

        if comment_schemas:
            try:
                await comment_repo.bulk_create(comment_schemas)
            except Exception as e:
                logger.error(f"Failed to bulk store comments in DB: {e}")

    async def store_creator(self, items: list[dict]):
        session = await self._get_session()
        author_repo = AuthorRepository(session)

        author_schemas = []
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
                author_schemas.append(author_schema)
            except Exception as e:
                logger.error(f"Failed to process creator item for DB: {e}")

        if author_schemas:
            try:
                await author_repo.bulk_create_or_update(author_schemas)
            except Exception as e:
                logger.error(f"Failed to bulk store creators in DB: {e}")

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
