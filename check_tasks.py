import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_tasks():
    engine = create_async_engine("postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT task_type, status, error_message, COUNT(*) FROM crawl_tasks GROUP BY task_type, status, error_message"))
        print(f"{'Type':<15} | {'Status':<15} | {'Count':<5} | {'Error'}")
        print("-" * 60)
        for row in result:
            print(f"{row[0]:<15} | {row[1]:<15} | {row[3]:<5} | {row[2]}")

if __name__ == "__main__":
    asyncio.run(check_tasks())
