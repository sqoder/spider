import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

# First, patch config to use sqlite
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_crawler.db"

from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.repositories.task_repo import TaskRepository
from app.repositories.post_repo import PostRepository
from app.repositories.author_repo import AuthorRepository
from app.schemas.task import TaskCreate
from app.crawlers.base import CrawlResult
from app.workers.crawler_worker import _execute_task_async

async def setup_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

async def run_test():
    await setup_db()
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. Create a task
        task_repo = TaskRepository(session)
        task_data = TaskCreate(
            platform="youtube",
            task_type="search",
            keyword="mock test",
            limit_count=2
        )
        task = await task_repo.create(task_data)
        task_id = task.id
        
    print(f"Created task {task_id}")
    
    # 2. Mock Crawler Factory and Redis
    mock_crawler = AsyncMock()
    # Mock search result returning 2 dummy results
    mock_crawler.search.return_value = [
        CrawlResult(
            platform="youtube",
            source_id="vid_1",
            title="Mock Video 1",
            content="Description 1",
            content_type="video",
            author_id="channel_1",
            author_name="Mock Channel",
            author_username="mockchannel",
            like_count=100,
            view_count=5000,
            published_at=datetime.utcnow(),
            raw={"dummy": "data"}
        ),
        CrawlResult(
            platform="youtube",
            source_id="vid_2",
            title="Mock Video 2",
            content="Description 2",
            content_type="video",
            author_id="channel_1",
            author_name="Mock Channel",
            author_username="mockchannel",
            like_count=200,
            view_count=10000,
            published_at=datetime.utcnow(),
            raw={"dummy": "data2"}
        )
    ]
    
    with patch("app.workers.crawler_worker.CrawlerFactory.create", return_value=mock_crawler), \
         patch("app.storage.redis.redis_storage") as mock_redis:
        
        mock_redis.set_task_progress = AsyncMock()
        
        # 3. Run the async worker function directly
        print("Running worker...")
        await _execute_task_async(task_id)
        
    # 4. Verify the database
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        post_repo = PostRepository(session)
        author_repo = AuthorRepository(session)
        
        task = await task_repo.get_by_id(task_id)
        print(f"Task status: {task.status}, success_count: {task.success_count}")
        from sqlalchemy import select
        from app.models.post import Post
        from app.models.author import Author
        
        result = await session.execute(select(Post))
        posts = result.scalars().all()
        print(f"Saved posts count: {len(posts)}")
        for p in posts:
            print(f" - Post: {p.title} (ID: {p.source_id})")
            
        result = await session.execute(select(Author))
        authors = result.scalars().all()
        print(f"Saved authors count: {len(authors)}")
        for a in authors:
            print(f" - Author: {a.display_name} (ID: {a.source_id})")

if __name__ == "__main__":
    asyncio.run(run_test())
