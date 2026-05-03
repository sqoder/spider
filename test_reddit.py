import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_crawler.db"

from app.crawlers.base import CrawlResult
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.repositories.author_repo import AuthorRepository
from app.repositories.post_repo import PostRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate
from app.workers.crawler_worker import _execute_task_async


async def setup_db():
    engine = get_engine()
    async with engine.begin() as conn:
        # Keep tables to test incremental inserts
        await conn.run_sync(Base.metadata.create_all)


async def run_test():
    await setup_db()

    session_factory = get_session_factory()
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task_data = TaskCreate(
            platform="reddit", task_type="search", keyword="OpenAI", limit_count=2
        )
        task = await task_repo.create(task_data)
        task_id = task.id

    print(f"Created task {task_id}")

    # Mock Reddit Crawler to avoid needing real API keys
    mock_crawler = AsyncMock()
    mock_crawler.search.return_value = [
        CrawlResult(
            platform="reddit",
            source_id="t3_12345a",
            title="OpenAI announces new model",
            content="This is the content of the Reddit post.",
            content_type="text",
            author_id="t2_abcdef",
            author_name="redditor123",
            author_username="redditor123",
            like_count=5000,
            comment_count=150,
            published_at=datetime.utcnow(),
            raw={"dummy": "reddit_data_1"},
        ),
        CrawlResult(
            platform="reddit",
            source_id="t3_12345b",
            title="How to use the new OpenAI API",
            content="Here is a tutorial...",
            content_type="text",
            author_id="t2_abcdef",  # Same author
            author_name="redditor123",
            author_username="redditor123",
            like_count=2000,
            comment_count=80,
            published_at=datetime.utcnow(),
            raw={"dummy": "reddit_data_2"},
        ),
    ]

    with patch(
        "app.workers.crawler_worker.CrawlerFactory.create", return_value=mock_crawler
    ), patch("app.storage.redis.redis_storage") as mock_redis:

        mock_redis.set_task_progress = AsyncMock()

        print("Running worker for Reddit...")
        await _execute_task_async(task_id)

    # Verify the database
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        print(f"Task status: {task.status}, success_count: {task.success_count}")

        from sqlalchemy import select

        from app.models.author import Author
        from app.models.post import Post

        # Check Reddit posts
        result = await session.execute(select(Post).where(Post.platform == "reddit"))
        posts = result.scalars().all()
        print(f"Saved Reddit posts count: {len(posts)}")
        for p in posts:
            print(f" - Post: {p.title} (ID: {p.source_id}, Likes: {p.like_count})")

        # Check Reddit authors
        result = await session.execute(
            select(Author).where(Author.platform == "reddit")
        )
        authors = result.scalars().all()
        print(f"Saved Reddit authors count: {len(authors)}")
        for a in authors:
            print(f" - Author: {a.display_name} (ID: {a.source_id})")


if __name__ == "__main__":
    asyncio.run(run_test())
