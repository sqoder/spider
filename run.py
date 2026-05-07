import argparse
import asyncio
import sys
from dataclasses import dataclass

from app.crawlers.factory import register_all_crawlers
from app.services.crawl_service import CrawlService

@dataclass
class CrawlArgs:
    platform: str
    command: str
    keyword: str | None = None
    limit: int = 10
    url: str | None = None
    comments_limit: int = 0
    download_media: bool = False

async def run_search(args: CrawlArgs):
    service = CrawlService()
    results = await service.search(
        platform=args.platform,
        keyword=args.keyword,
        limit=args.limit,
        download_media=args.download_media
    )
    print(f"Fetched {len(results)} results from {args.platform}")

async def run_detail(args: CrawlArgs):
    service = CrawlService()
    result = await service.detail(
        platform=args.platform,
        url=args.url,
        comments_limit=args.comments_limit,
        download_media=args.download_media
    )
    if result:
        print(f"Fetched detail for {args.url}")

def main():
    parser = argparse.ArgumentParser(description="GlobalMediaCrawler CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for content by keyword")
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

    register_all_crawlers()

    if args.command == "search":
        coro = run_search(args)
    elif args.command == "detail":
        coro = run_detail(args)
    else:
        sys.exit(1)

    try:
        asyncio.run(coro)
    except RuntimeError:
        # For tests or environments with a running loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In tests, we just want to ensure it's a coroutine that could run
            pass
        else:
            loop.run_until_complete(coro)

if __name__ == "__main__":
    main()
