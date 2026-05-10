"""
Quick start — minimal YouTube crawler usage.

Run:
  python examples/quick_start.py

Pulls 10 recent comments from a known video using the yt-dlp crawler
(no API key required).
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio

from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler


VIDEO_ID = "kJQP7kiw5Fk"   # Despacito — stable, always has plenty of comments


async def main():
    crawler = YtdlpYouTubeCrawler()
    try:
        print(f"Fetching 10 comments from https://youtu.be/{VIDEO_ID}\n")
        comments = await crawler.get_comments(VIDEO_ID, limit=10)

        print(f"Got {len(comments)} comments:\n")
        for i, c in enumerate(comments, 1):
            author = getattr(c, "author", "?")
            content = (getattr(c, "content", "") or "").replace("\n", " ")
            if len(content) > 80:
                content = content[:80] + "..."
            print(f"  {i:2d}. {author}: {content}")
    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
