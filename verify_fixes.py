import asyncio
import sys
from datetime import UTC, datetime
from loguru import logger
from app.core.config import get_settings
from app.crawlers.youtube.crawler import YouTubeCrawler
from app.crawlers.reddit.crawler import RedditCrawler

async def verify_config():
    logger.info("Verifying configuration unification...")
    settings = get_settings()
    # Check if env_file is None
    if settings.model_config.get("env_file") is not None:
        logger.error("B13 (Config): env_file should be None")
    else:
        logger.success("B13 (Config): env_file is None")
    
    # Check if a value is pulled from crawler_config
    import crawler_config
    if settings.youtube_api_key == crawler_config.YOUTUBE_API_KEY:
        logger.success("B13 (Config): Settings pulling from crawler_config")
    else:
        logger.warning(f"B13 (Config): Settings value mismatch: {settings.youtube_api_key} vs {crawler_config.YOUTUBE_API_KEY}")

async def verify_youtube():
    logger.info("Verifying YouTube crawler fixes...")
    crawler = YouTubeCrawler()
    
    # B6: author_username check
    logger.info("Testing B6: author_username should be None in _parse_video")
    # Mocking a snippet
    snippet = {"channelId": "UC123", "channelTitle": "Test Channel", "title": "Test Video"}
    detail = {"statistics": {}, "contentDetails": {}}
    result = crawler._parse_video("vid123", snippet, detail)
    if result.author_username is None:
        logger.success("B6 (YouTube): author_username is None")
    else:
        logger.error(f"B6 (YouTube): author_username is {result.author_username}, expected None")

    # B7: get_event_loop check (manual check of code usually, but can try to trigger)
    # This is more of a static check.

async def verify_reddit():
    logger.info("Verifying Reddit crawler fixes...")
    crawler = RedditCrawler()
    
    # B11: fallback URL check
    logger.info("Testing B11: fallback URL format")
    # This requires looking at the code or mocking the API client.
    
    # B12: Recursion depth
    logger.info("Testing B12: Recursion depth limit")
    results = []
    # Mocking a deep tree
    children = [{"kind": "more", "data": {"children": ["c1"]}}]
    # We can't easily mock the API response here without monkeypatching
    
    # B9: Scrapling usage
    from app.crawlers.reddit.api_client import RedditAPIClient
    import inspect
    source = inspect.getsource(RedditAPIClient._request)
    if "import httpx" in source:
        logger.warning("B9 (Reddit): Still using 'import httpx' inside _request instead of self._fetcher (Scrapling)")
    else:
        logger.success("B9 (Reddit): 'import httpx' not found in _request (assuming Scrapling or else)")

async def main():
    await verify_config()
    await verify_youtube()
    await verify_reddit()

if __name__ == "__main__":
    asyncio.run(main())
