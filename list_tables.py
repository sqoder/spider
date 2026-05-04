import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def list_tables():
    engine = create_async_engine("postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        for row in result:
            print(row[0])

if __name__ == "__main__":
    asyncio.run(list_tables())
