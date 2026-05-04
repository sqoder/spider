import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def reset_tasks():
    engine = create_async_engine("postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler")
    async with engine.begin() as conn:
        # Reset failed tasks to pending so they are retried by the fresh worker
        await conn.execute(text("UPDATE crawl_tasks SET status = 'pending', error_message = NULL WHERE status = 'failed'"))
        print("Reset all failed tasks to pending.")

if __name__ == "__main__":
    asyncio.run(reset_tasks())
