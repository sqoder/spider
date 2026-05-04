import asyncio
import os
from loguru import logger
from app.services.crawl_service import CrawlService
from app.db.session import get_session_factory
from app.core.config import get_settings
from app.crawlers.factory import register_all_crawlers

async def run_openai_crawl():
    # 0. Ensure native scraper mode is enabled
    settings = get_settings()
    settings.youtube_use_scraper = True # Force native scraper
    
    logger.info("Initializing Native Scraper (Keyless Mode)...")
    register_all_crawlers()

    # 1. Setup Database Session
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = CrawlService(session)
        
        platform = "youtube"
        keyword = "openai"
        limit = 20
        
        logger.info(f"🚀 Starting NATIVE CRAWL for '{keyword}' (Limit: {limit})...")
        
        try:
            # Trigger search and deep crawl (details + comments + media)
            result = await service.search(
                platform=platform,
                keyword=keyword,
                limit=limit,
                deep=True
            )
            
            logger.info(f"✅ Success! Found {len(result['items'])} items for '{keyword}'.")
            logger.info("📡 Background tasks are extracting deep comments and downloading media files.")
            
            # Show locations
            base = settings.save_data_path
            logger.info(f"📂 Posts: {base}/{platform}/jsonl/search_contents_*.jsonl")
            logger.info(f"💬 Comments: {base}/{platform}/jsonl/detail_comments_*.jsonl")
            logger.info(f"🎬 Media: {settings.media_storage_path}/{platform}/")

        except Exception as e:
            logger.error(f"❌ Crawl failed: {e}")

if __name__ == "__main__":
    # Ensure directories
    os.makedirs("data", exist_ok=True)
    os.makedirs("media", exist_ok=True)
    
    asyncio.run(run_openai_crawl())
