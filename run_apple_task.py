import asyncio
import os
from loguru import logger
from app.services.crawl_service import CrawlService
from app.db.session import get_session_factory
from app.core.config import get_settings

async def run_apple_crawl():
    # 0. Register crawlers
    from app.crawlers.factory import register_all_crawlers
    register_all_crawlers()

    # 1. Configuration check
    settings = get_settings()
    logger.info(f"Storage Option: {settings.save_data_option}")
    logger.info(f"Storage Path: {settings.save_data_path}")
    
    # 2. Setup Database Session
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = CrawlService(session)
        
        platform = "youtube"
        keyword = "apple"
        limit = 20
        
        logger.info(f"Starting crawl for keyword '{keyword}' on {platform}...")
        
        # 3. Search and Deep Crawl
        # Setting deep=True will automatically trigger:
        # - Detail extraction for each video
        # - Comment extraction (including nested replies)
        # - Media download (video/cover) via Celery
        try:
            result = await service.search(
                platform=platform,
                keyword=keyword,
                limit=limit,
                deep=True
            )
            
            logger.info(f"Search completed. Found {len(result['items'])} items.")
            logger.info("Deep tasks (details, comments, media) have been queued in Celery.")
            
            # Print storage paths for the user
            base = settings.save_data_path
            option = settings.save_data_option
            logger.info(f"Main posts saved to: {base}/{platform}/{option}/search_contents_*.{option}")
            logger.info(f"Comments will be saved to: {base}/{platform}/{option}/detail_comments_*.{option}")
            logger.info(f"Videos/Images will be saved to: {settings.media_storage_path}/{platform}/")

        except Exception as e:
            logger.error(f"Crawl failed: {e}")

if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs("data", exist_ok=True)
    os.makedirs("media", exist_ok=True)
    
    asyncio.run(run_apple_crawl())
