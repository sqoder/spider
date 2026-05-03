import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_crawler.db"

from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate
from app.workers.crawler_worker import _execute_task_async

async def setup_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def run_test():
    await setup_db()
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task_data = TaskCreate(
            platform="x",
            task_type="search",
            keyword="Elon Musk",
            limit_count=1
        )
        task = await task_repo.create(task_data)
        task_id = task.id
        
    print(f"Created task {task_id}")
    
    # Mock twscrape API and Tweet objects
    mock_api = AsyncMock()
    
    # Create a mock tweet object that mimics twscrape.models.Tweet
    mock_tweet = MagicMock()
    mock_tweet.id = 1800000000000000000
    mock_tweet.rawContent = "We are launching a new rocket tomorrow! 🚀"
    mock_tweet.likeCount = 850000
    mock_tweet.replyCount = 42000
    mock_tweet.retweetCount = 125000
    mock_tweet.viewCount = 15000000
    mock_tweet.date = datetime.utcnow()
    mock_tweet.media = None
    mock_tweet.dict.return_value = {"dummy": "data"}
    
    # Create a mock user object
    mock_user = MagicMock()
    mock_user.id = 44196397
    mock_user.username = "elonmusk"
    mock_user.displayname = "Elon Musk"
    mock_user.profileImageUrl = "https://x.com/elon_avatar.jpg"
    mock_tweet.user = mock_user

    # Setup the async generator for search
    async def mock_search_gen(*args, **kwargs):
        yield mock_tweet

    mock_api.search = mock_search_gen
    
    with patch("app.crawlers.x.crawler.XCrawler._get_pool", return_value=mock_api), \
         patch("app.storage.redis.redis_storage") as mock_redis:
        
        mock_redis.set_task_progress = AsyncMock()
        
        print("Running worker for X/Twitter search...")
        await _execute_task_async(task_id)
        
    # Verify the database
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        print(f"Task status: {task.status}, success_count: {task.success_count}")
        
        from sqlalchemy import select
        from app.models.post import Post
        from app.models.author import Author
        
        result = await session.execute(select(Post).where(Post.platform == "x"))
        posts = result.scalars().all()
        print(f"Saved X/Twitter posts count: {len(posts)}")
        for p in posts:
            print(f" - Post: {p.content[:30]}... (ID: {p.source_id}) [Views: {p.view_count}]")
            
        result = await session.execute(select(Author).where(Author.platform == "x"))
        authors = result.scalars().all()
        print(f"Saved X/Twitter authors count: {len(authors)}")
        for a in authors:
            print(f" - Author: {a.display_name} (@{a.username})")

if __name__ == "__main__":
    asyncio.run(run_test())
