import os
import importlib.util
import asyncio
from loguru import logger
from app.crawlers.factory import register_all_crawlers
from app.services.crawl_service import CrawlService

def parse_user_handle(platform: str, input_value: str) -> str:
    """Extracts username handle or channel ID from a profile URL if provided."""
    if not input_value:
        return ""
    input_value = input_value.strip()
    if not (input_value.startswith("http://") or input_value.startswith("https://")):
        return input_value

    from urllib.parse import urlparse
    parsed = urlparse(input_value)
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]

    if not parts:
        return input_value

    platform = platform.lower()
    if platform == "youtube":
        if parts[0].startswith("@"):
            return parts[0]
        if len(parts) >= 2 and parts[0] in ("user", "channel", "c"):
            return parts[1]
        return parts[0]
    elif platform == "instagram":
        return parts[0]
    elif platform == "tiktok":
        return parts[0].lstrip("@")
    elif platform in ("x", "twitter"):
        return parts[0]
    elif platform == "reddit":
        if len(parts) >= 2 and parts[0] in ("user", "u"):
            return parts[1]
        return parts[0]

    return parts[-1]

async def run_with_config(config_path: str = "crawler_config.py"):
    """Reads flat variables from crawler_config.py and executes crawl jobs."""
    if not os.path.exists(config_path):
        config_path = "examples/crawler_config.example.py"
        if not os.path.exists(config_path):
            print(f"Configuration file {config_path} not found.")
            return

    print(f"\n[Config Mode] Reading configuration from: {config_path}")
    spec = importlib.util.spec_from_file_location("crawler_config", config_path)
    if not spec or not spec.loader:
        print(f"Failed to load configuration from {config_path}")
        return
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

    # 1. Retrieve flat variables from the config module
    enabled_platforms = [p.lower().strip() for p in getattr(config, "ENABLED_PLATFORMS", []) if p]
    crawl_mode = getattr(config, "CRAWL_MODE", "keyword").lower().strip()  # "keyword" | "url" | "user"
    keyword = getattr(config, "KEYWORD", "")
    limit = getattr(config, "LIMIT", 10)
    urls = getattr(config, "URLS", [])
    user_handle = getattr(config, "USER_HANDLE", "")
    user_post_limit = getattr(config, "USER_POST_LIMIT", 10)

    download_comments = getattr(config, "DOWNLOAD_COMMENTS", False)
    comments_limit = getattr(config, "COMMENTS_LIMIT", 0) if download_comments else 0
    download_media = getattr(config, "DOWNLOAD_MEDIA", False)

    # 2. Override global runtime settings dynamically from config
    from app.core.config import get_settings
    settings = get_settings()

    save_format = getattr(config, "SAVE_FORMAT", "csv").lower()
    if save_format in ("database", "db"):
        settings.save_data_option = "db"
    else:
        settings.save_data_option = save_format

    save_path = getattr(config, "SAVE_PATH", "./output")
    if save_path:
        settings.save_data_path = save_path
        settings.media_storage_path = save_path

    # Dynamic comment and media controls mapping
    settings.crawl_comments_enabled = download_comments
    settings.crawl_comments_count = comments_limit
    settings.crawl_comments_include_replies = getattr(config, "DOWNLOAD_REPLIES", False)
    settings.crawl_media_enabled = download_media
    settings.media_quality = getattr(config, "MEDIA_QUALITY", 360)
    m_types = getattr(config, "MEDIA_TYPES", ["video", "image"])
    settings.media_types = ",".join(m_types) if isinstance(m_types, list) else str(m_types)

    # Custom Database connection URL mapping
    db_uri = getattr(config, "DATABASE_URI", "")
    if db_uri:
        settings.database_url = db_uri

    # API Keys & Cookies dynamic mapping
    yt_key = getattr(config, "YOUTUBE_API_KEY", "")
    if yt_key:
        settings.youtube_api_key = yt_key

    reddit_id = getattr(config, "REDDIT_CLIENT_ID", "")
    if reddit_id:
        settings.reddit_client_id = reddit_id
    reddit_secret = getattr(config, "REDDIT_CLIENT_SECRET", "")
    if reddit_secret:
        settings.reddit_client_secret = reddit_secret

    yt_cookies = getattr(config, "YOUTUBE_COOKIES_FILE", "")
    if yt_cookies:
        settings.youtube_cookies_file = yt_cookies
    tiktok_cookies = getattr(config, "TIKTOK_COOKIES_FILE", "")
    if tiktok_cookies:
        settings.tiktok_cookies_file = tiktok_cookies
    insta_cookies = getattr(config, "INSTAGRAM_COOKIES_FILE", "")
    if insta_cookies:
        settings.instagram_cookies_file = insta_cookies
    x_accounts = getattr(config, "X_ACCOUNTS_FILE", "")
    if x_accounts:
        settings.x_accounts_file = x_accounts

    proxy_url = getattr(config, "PROXY_URL", "")
    if proxy_url:
        settings.proxy_url = proxy_url
    settings.proxy_rotation = getattr(config, "PROXY_ROTATION", False)

    if not enabled_platforms:
        print("No enabled platforms specified in ENABLED_PLATFORMS.")
        return

    # Automatically register crawlers
    register_all_crawlers()
    service = CrawlService()

    for platform in enabled_platforms:
        print(f"\n==========================================")
        print(f"Starting crawl for platform: {platform}")
        print(f"==========================================")

        if crawl_mode == "url":
            if not urls:
                print(f"[{platform}] URLS list is empty in config.")
                continue
            for url in urls:
                print(f"[{platform}] Processing specific URL: {url} (comments: {comments_limit}, media: {download_media})")
                try:
                    await service.detail(
                        platform=platform,
                        url=url,
                        comments_limit=comments_limit,
                        download_media=download_media
                    )
                except Exception as e:
                    print(f"[{platform}] Failed to process URL {url}: {e}")

        elif crawl_mode == "user":
            if not user_handle:
                print(f"[{platform}] USER_HANDLE is not set in config.")
                continue

            # Auto-extract handle from profile URL if provided
            final_handle = parse_user_handle(platform, user_handle)
            if final_handle != user_handle:
                print(f"[{platform}] Automatically parsed profile URL to handle: '{final_handle}'")

            print(f"[{platform}] Fetching posts for user: {final_handle} (limit: {user_post_limit}, download_media: {download_media})")
            try:
                from app.crawlers.factory import CrawlerFactory
                crawler = CrawlerFactory.create(platform)
                try:
                    results = await crawler.get_user_posts(final_handle, limit=user_post_limit)
                    result_dicts = [res.to_dict() for res in results]
                    from app.storage.factory import StoreFactory
                    store = StoreFactory.create_store(platform, "user_posts")
                    try:
                        await store.store_content(result_dicts)
                    finally:
                        await store.close()
                    print(f"[{platform}] Successfully processed {len(result_dicts)} user posts list.")

                    # Deep crawling: automatically pull details & comments for each post on the user's feed
                    if download_comments or download_media:
                        print(f"[{platform}] Deep-fetching details & comments for {len(results)} user posts...")
                        for i, post in enumerate(results):
                            post_url = getattr(post, "url", None)
                            if post_url:
                                print(f"[{platform}] -> Deep-fetching post: {post_url}")
                                # Add a delay to avoid rate limiting
                                if i > 0 and platform == "reddit":
                                    logger.info("Adding a 2-second delay to avoid Reddit rate limits...")
                                    await asyncio.sleep(2)
                                try:
                                    await service.detail(
                                        platform=platform,
                                        url=post_url,
                                        comments_limit=comments_limit,
                                        download_media=download_media
                                    )
                                except Exception as de:
                                    print(f"[{platform}] Failed to parse details for {post_url}: {de}")
                finally:
                    await crawler.close()
            except Exception as e:
                print(f"[{platform}] Failed to fetch user posts: {e}")

        else:  # "keyword" mode
            if not keyword:
                print(f"[{platform}] KEYWORD is empty in config.")
                continue
            print(f"[{platform}] Searching keyword: '{keyword}' (limit: {limit}, download_media: {download_media})")
            try:
                results = await service.search(
                    platform=platform,
                    keyword=keyword,
                    limit=limit,
                    download_media=download_media
                )
                print(f"[{platform}] Successfully processed {results.count} posts.")

                # Fetch comments for posts if enabled
                if comments_limit > 0 and results.items:
                    print(f"[{platform}] Fetching up to {comments_limit} comments for each post...")
                    for i, r in enumerate(results.items):
                        url = r.get("url")
                        if url:
                            if "/channel/" in url or "/user/" in url or "/@" in url or "youtube.com/c/" in url:
                                logger.info(f"[{platform}] Skipping non-video channel URL: {url}")
                                continue
                            
                            # Add a delay to avoid rate limiting, especially for reddit
                            if i > 0 and platform == "reddit":
                                logger.info("Adding a 2-second delay to avoid Reddit rate limits...")
                                await asyncio.sleep(2)

                            try:
                                await service.detail(
                                    platform=platform,
                                    url=url,
                                    comments_limit=comments_limit,
                                    download_media=download_media
                                )
                            except Exception as e:
                                logger.debug(f"[{platform}] Failed to fetch comments for {url}: {e}")
            except Exception as e:
                print(f"[{platform}] Failed to execute search for keyword '{keyword}': {e}")
