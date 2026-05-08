import asyncio
import sys
from datetime import UTC, datetime

# Simple logger
class Logger:
    def info(self, msg): print(f"[INFO] {msg}")
    def success(self, msg): print(f"[SUCCESS] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")
    def warning(self, msg): print(f"[WARNING] {msg}")

logger = Logger()

# Mock settings and crawlers
try:
    from app.core.config import get_settings
    from app.crawlers.youtube.crawler import YouTubeCrawler
    from app.crawlers.reddit.crawler import RedditCrawler
    from app.crawlers.reddit.api_client import RedditAPIClient
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

async def verify_config():
    logger.info("Verifying configuration unification...")
    settings = get_settings()
    if settings.model_config.get("env_file") is not None:
        logger.error("Config: env_file should be None")
    else:
        logger.success("Config: env_file is None")
    
    import crawler_config
    if settings.youtube_api_key == crawler_config.YOUTUBE_API_KEY:
        logger.success("Config: Settings pulling from crawler_config")
    else:
        logger.warning(f"Config: Settings value mismatch: '{settings.youtube_api_key}' vs '{crawler_config.YOUTUBE_API_KEY}'")
    
    if hasattr(settings, "max_retries"):
        logger.success(f"Config: max_retries exists ({settings.max_retries})")
    else:
        logger.error("Config: max_retries missing from Settings")

async def verify_youtube():
    logger.info("Verifying YouTube crawler fixes...")
    crawler = YouTubeCrawler()
    
    # B6: author_username check
    snippet = {"channelId": "UC123", "channelTitle": "Test Channel", "title": "Test Video"}
    detail = {"statistics": {}, "contentDetails": {}}
    result = crawler._parse_video("vid123", snippet, detail)
    if result.author_username is None:
        logger.success("B6 (YouTube): author_username is None")
    else:
        logger.error(f"B6 (YouTube): author_username is {result.author_username}, expected None")

async def verify_reddit():
    logger.info("Verifying Reddit API Client...")
    client = RedditAPIClient()
    if hasattr(client, "_fetcher"):
        logger.success("B9 (Reddit): client._fetcher exists (Scrapling)")
    else:
        logger.error("B9 (Reddit): client._fetcher missing")
    
    import inspect
    source = inspect.getsource(client._request)
    if "f.get" in source or "f.post" in source:
        logger.success("B9 (Reddit): _request uses fetcher (f.get/f.post)")
    else:
        logger.error("B9 (Reddit): _request does NOT seem to use fetcher correctly")

async def main():
    await verify_config()
    await verify_youtube()
    await verify_reddit()

if __name__ == "__main__":
    asyncio.run(main())
