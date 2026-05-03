import asyncio
import os

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

    # Instagram public post (e.g. Cristiano Ronaldo post)
    # https://www.instagram.com/p/C1tGv_8LwB_/

    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task_data = TaskCreate(
            platform="instagram",
            task_type="post_detail",
            url="https://www.instagram.com/p/C1tGv_8LwB_/",
            limit_count=1,
        )
        task = await task_repo.create(task_data)
        task_id = task.id

    print(f"Created task {task_id}")

    from unittest.mock import AsyncMock, patch

    with patch("app.storage.redis.redis_storage") as mock_redis, patch(
        "app.crawlers.instagram.crawler.GalleryDLClient.extract_metadata",
        new_callable=AsyncMock,
    ) as mock_extract:

        mock_redis.set_task_progress = AsyncMock()
        mock_extract.return_value = [
            {
                "shortcode": "C1tGv_8LwB_",
                "typename": "GraphImage",
                "display_url": "https://fake-ig-url.com/image.jpg",
                "owner": {
                    "id": "12345678",
                    "username": "cristiano",
                    "full_name": "Cristiano Ronaldo",
                },
                "edge_media_to_caption": {
                    "edges": [{"node": {"text": "A great game! ⚽️"}}]
                },
                "edge_media_preview_like": {"count": 10500000},
                "edge_media_to_comment": {"count": 55000},
                "taken_at_timestamp": 1704456000,
            }
        ]

        print("Running worker for Instagram single post...")
        await _execute_task_async(task_id)

    # Verify the database
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        print(f"Task status: {task.status}, success_count: {task.success_count}")

        from sqlalchemy import select

        from app.models.author import Author
        from app.models.post import Post

        result = await session.execute(select(Post).where(Post.platform == "instagram"))
        posts = result.scalars().all()
        print(f"Saved Instagram posts count: {len(posts)}")
        for p in posts:
            print(f" - Post: {p.content[:30]}... (ID: {p.source_id})")

        result = await session.execute(
            select(Author).where(Author.platform == "instagram")
        )
        authors = result.scalars().all()
        print(f"Saved Instagram authors count: {len(authors)}")
        for a in authors:
            print(f" - Author: {a.display_name} (ID: {a.source_id})")


if __name__ == "__main__":
    asyncio.run(run_test())
