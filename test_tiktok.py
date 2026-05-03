import asyncio
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_crawler.db"

from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.repositories.task_repo import TaskRepository
from app.repositories.post_repo import PostRepository
from app.repositories.author_repo import AuthorRepository
from app.schemas.task import TaskCreate
from app.workers.crawler_worker import _execute_task_async

async def setup_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def run_test():
    await setup_db()
    session_factory = get_session_factory()
    
    # We will test getting a single TikTok video
    # url: https://www.tiktok.com/@tiktok/video/7106594312292453675
    
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task_data = TaskCreate(
            platform="tiktok",
            task_type="post_detail",
            url="https://www.tiktok.com/@tiktok/video/7106594312292453675",
            limit_count=1
        )
        task = await task_repo.create(task_data)
        task_id = task.id
        
    print(f"Created task {task_id}")
    
    from unittest.mock import AsyncMock, patch
    with patch("app.storage.redis.redis_storage") as mock_redis:
        mock_redis.set_task_progress = AsyncMock()
        
        print("Running worker for TikTok single video...")
        await _execute_task_async(task_id)
        
    # Verify the database
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        print(f"Task status: {task.status}, success_count: {task.success_count}")
        
        from sqlalchemy import select
        from app.models.post import Post
        from app.models.author import Author
        
        # Check TikTok posts
        result = await session.execute(select(Post).where(Post.platform == "tiktok"))
        posts = result.scalars().all()
        print(f"Saved TikTok posts count: {len(posts)}")
        for p in posts:
            print(f" - Post: {p.title[:30]}... (ID: {p.source_id}, Views: {p.view_count})")
            
        # Check TikTok authors
        result = await session.execute(select(Author).where(Author.platform == "tiktok"))
        authors = result.scalars().all()
        print(f"Saved TikTok authors count: {len(authors)}")
        for a in authors:
            print(f" - Author: {a.display_name} (ID: {a.source_id})")

if __name__ == "__main__":
    asyncio.run(run_test())
