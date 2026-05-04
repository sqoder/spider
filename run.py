#!/usr/bin/env python3
"""
Run YouTube crawl based on config.py settings.

Usage:
    python run.py

Three modes (set CRAWL_MODE in config.py):
    keyword  - Search by keyword
    url      - Crawl specific video URLs
    user     - Crawl videos from a user/channel
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure we're in project root
os.chdir(Path(__file__).parent)

# === Generate run timestamp (used for output isolation) ===
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# === Load user config ===
import config as cfg  # noqa: E402

# === Set environment for app modules ===
# These must be set BEFORE any get_settings() call
os.environ.setdefault("SIMPLE_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/crawler.db")
os.environ.setdefault("YOUTUBE_API_KEY", "")
os.environ.setdefault("ENABLED_PLATFORMS", "youtube")
os.environ.setdefault("SAVE_DATA_OPTION", "csv")
os.environ.setdefault("SAVE_DATA_PATH", "output")

# Force timestamp subdir so each run produces separate output
os.environ["SAVE_DATA_SUBDIR"] = f"{RUN_TIMESTAMP}/text/csv"

# Apply config.py overrides
os.environ["CRAWL_SEARCH_LIMIT"] = str(cfg.SEARCH_LIMIT)
os.environ["CRAWL_COMMENTS_COUNT"] = str(cfg.COMMENTS_COUNT)
os.environ["CRAWL_COMMENTS_ENABLED"] = str(cfg.COMMENTS_ENABLED).lower()
os.environ["CRAWL_COMMENTS_INCLUDE_REPLIES"] = str(cfg.INCLUDE_REPLIES).lower()
os.environ["CRAWL_MEDIA_ENABLED"] = str(cfg.MEDIA_ENABLED).lower()

# === App imports ===
from app.crawlers.factory import CrawlerFactory, register_all_crawlers  # noqa: E402
from app.storage.factory import StoreFactory  # noqa: E402

register_all_crawlers()


async def download_media(url: str, source_id: str):
    """Download thumbnail + video via yt-dlp."""
    if not cfg.MEDIA_ENABLED:
        return
    media_dir = Path("output") / "youtube" / RUN_TIMESTAMP / "media" / source_id
    media_dir.mkdir(parents=True, exist_ok=True)

    # Thumbnail
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--write-info-json", "--skip-download", "--no-playlist",
        "-o", str(media_dir / "video"), url,
    )
    await proc.wait()

    # Video
    q = cfg.MEDIA_QUALITY
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "-f", f"bestvideo[height<={q}]+bestaudio/best[height<={q}]",
        "--merge-output-format", "mp4", "--no-playlist", "--ignore-errors",
        "-o", str(media_dir / "video.%(ext)s"), url,
    )
    await proc.wait()

    for f in sorted(media_dir.iterdir()):
        print(f"      {f.name} ({f.stat().st_size / 1024:.1f} KB)")


async def process_detail(crawler, result, index: int, total: int):
    """Fetch detail, comments, and media for a single crawl result."""
    print(f"\n--- [{index}/{total}] {result.title} ---")
    print(f"    URL: {result.url}")

    detail = await crawler.get_post_detail(result.url)
    metrics = detail.to_dict().get("metrics", {})
    print(f"    Views: {metrics.get('view_count', 0):,} | Likes: {metrics.get('like_count', 0):,}")

    # Save detail
    dstore = StoreFactory.create_store("youtube", "detail")
    try:
        await dstore.store_content([detail.to_dict()])

        # Comments
        if cfg.COMMENTS_ENABLED:
            comments = await crawler.get_comments(detail.source_id, limit=cfg.COMMENTS_COUNT)
            if not cfg.INCLUDE_REPLIES:
                comments = [c for c in comments if not c.parent_comment_id]
            if comments:
                await dstore.store_comment(detail.source_id, [c.to_dict() for c in comments])
            print(f"    评论: {len(comments)} 条")
        else:
            print(f"    评论: 已关闭")
    finally:
        await dstore.close()

    # Media
    if cfg.MEDIA_ENABLED:
        print(f"    媒体: 下载中...")
        await download_media(result.url, detail.source_id)
    else:
        print(f"    媒体: 已关闭")


async def crawl_keyword():
    """Keyword search mode."""
    crawler = CrawlerFactory.create("youtube")
    try:
        results = await crawler.search(cfg.SEARCH_KEYWORD, limit=cfg.SEARCH_LIMIT)
        print(f"\n=== 关键词搜索模式: '{cfg.SEARCH_KEYWORD}' → {len(results)} 条结果 ===")

        # Save search results
        store = StoreFactory.create_store("youtube", "search")
        try:
            await store.store_content([r.to_dict() for r in results])
        finally:
            await store.close()

        # Detail for each
        for i, r in enumerate(results, 1):
            await process_detail(crawler, r, i, len(results))
    finally:
        await crawler.close()


async def crawl_urls():
    """URL crawl mode."""
    from app.crawlers.base import CrawlResult

    crawler = CrawlerFactory.create("youtube")
    try:
        results = []
        for url in cfg.CRAWL_URLS:
            results.append(CrawlResult(platform="youtube", source_id="", url=url, title=url))

        print(f"\n=== URL 抓取模式: {len(results)} 个链接 ===")

        for i, r in enumerate(results, 1):
            await process_detail(crawler, r, i, len(results))
    finally:
        await crawler.close()


async def crawl_user():
    """User channel crawl mode."""
    crawler = CrawlerFactory.create("youtube")
    try:
        results = await crawler.get_user_posts(cfg.USER_HANDLE, limit=cfg.USER_POST_LIMIT)
        print(f"\n=== 用户帖子抓取模式: @{cfg.USER_HANDLE} → {len(results)} 条帖子 ===")

        store = StoreFactory.create_store("youtube", "user_posts")
        try:
            await store.store_content([r.to_dict() for r in results])
        finally:
            await store.close()

        for i, r in enumerate(results, 1):
            await process_detail(crawler, r, i, len(results))
    finally:
        await crawler.close()


def show_output_tree():
    """Print this run's output file tree."""
    run_root = Path("output") / "youtube" / RUN_TIMESTAMP
    if not run_root.exists():
        return

    print(f"\n=== 输出文件 (youtube/{RUN_TIMESTAMP}) ===")
    for f in sorted(run_root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(Path("output"))
            print(f"  {rel} ({f.stat().st_size / 1024:.1f} KB)")


async def main():
    mode = cfg.CRAWL_MODE
    print(f"运行时间: {RUN_TIMESTAMP}")
    print(f"抓取模式: {mode}")
    print(f"评论: {'开启(' + str(cfg.COMMENTS_COUNT) + '条)' if cfg.COMMENTS_ENABLED else '关闭'} "
          f"| 二级评论: {'开启' if cfg.INCLUDE_REPLIES else '关闭(仅一级)'} "
          f"| 媒体: {'开启' if cfg.MEDIA_ENABLED else '关闭'}")

    if mode == "keyword":
        await crawl_keyword()
    elif mode == "url":
        await crawl_urls()
    elif mode == "user":
        await crawl_user()
    else:
        print(f"未知模式: {mode}，请在 config.py 中设置 CRAWL_MODE = 'keyword' | 'url' | 'user'")
        return

    show_output_tree()


if __name__ == "__main__":
    asyncio.run(main())
