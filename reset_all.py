import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def reset_all_details():
    engine = create_async_engine("postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler")
    async with engine.begin() as conn:
        # Reset ALL post_detail tasks so we re-download everything and ensure they stay on disk
        await conn.execute(text("UPDATE crawl_tasks SET status = 'pending', error_message = NULL WHERE task_type = 'post_detail'"))
        print("Reset all detail tasks to pending.")

if __name__ == "__main__":
    asyncio.run(reset_all_details())
