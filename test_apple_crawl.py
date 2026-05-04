import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.db.session import get_session_factory
from app.services.crawl_service import CrawlService
from app.crawlers.factory import register_all_crawlers

async def run_crawl():
    # Register crawlers
    register_all_crawlers()
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = CrawlService(session)
        print("Starting deep crawl for 'apple' with limit 50...")
        # platform="youtube", keyword="apple", limit=50, deep=True
        # We set deep=True so it triggers a detail crawl for each result
        result = await service.search(platform="youtube", keyword="apple", limit=50, deep=True)
        print(f"Initial search found {result['count']} items.")
        print("Deep crawl tasks (50 items) have been queued in the background.")
        print("Wait for the workers to process them. You can monitor 'media/youtube' for video files.")

if __name__ == "__main__":
    asyncio.run(run_crawl())
