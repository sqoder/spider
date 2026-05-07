#!/usr/bin/env python3
"""
GlobalMediaCrawler CLI Runner
A thin wrapper around CrawlService for production orchestration.
"""

import asyncio
import argparse
import sys
import os
from loguru import logger

from app.services.crawl_service import CrawlService
from app.crawlers.factory import register_all_crawlers
from app.core.config import get_settings

# Default to SQLite for CLI if no DATABASE_URL is set
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/crawler.db"

async def run_search(args):
    service = CrawlService()
    logger.info(f"Searching {args.platform} for '{args.keyword}' (limit: {args.limit}, download_media: {args.download_media})...")
    try:
        res = await service.search(
            platform=args.platform,
            keyword=args.keyword,
            limit=args.limit,
            download_media=args.download_media
        )
        logger.info(f"Search completed. Found {res.count} items.")
    except Exception as e:
        logger.error(f"Search failed: {e}")
        sys.exit(1)

async def run_detail(args):
    service = CrawlService()
    logger.info(f"Fetching detail for {args.url} on {args.platform} (comments_limit: {args.comments_limit}, download_media: {args.download_media})...")
    try:
        res = await service.detail(
            platform=args.platform,
            url=args.url,
            comments_limit=args.comments_limit,
            download_media=args.download_media
        )
        logger.info(f"Detail fetched: {res.data.get('title', 'No Title')}")
        logger.info(f"Comments: {len(res.comments)}")
    except Exception as e:
        logger.error(f"Detail fetch failed: {e}")
        sys.exit(1)

def main():
    register_all_crawlers()
    
    parser = argparse.ArgumentParser(description="Global Media Crawler CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for content on a platform")
    search_parser.add_argument("--platform", required=True, help="Platform to crawl (e.g., youtube, reddit, tiktok, instagram, x)")
    search_parser.add_argument("--keyword", required=True, help="Keyword to search for")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to fetch")
    search_parser.add_argument("--download-media", action="store_true", help="Whether to download associated media files")

    # Detail command
    detail_parser = subparsers.add_parser("detail", help="Get specific post detail and comments")
    detail_parser.add_argument("--platform", required=True, help="Platform of the post")
    detail_parser.add_argument("--url", required=True, help="URL of the post")
    detail_parser.add_argument("--comments-limit", type=int, default=0, help="Maximum number of comments to fetch")
    detail_parser.add_argument("--download-media", action="store_true", help="Whether to download associated media files")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "search":
        asyncio.run(run_search(args))
    elif args.command == "detail":
        asyncio.run(run_detail(args))

if __name__ == "__main__":
    main()
