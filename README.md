# youtube-crawler

Open-source YouTube data collector. Ready to use out of the box for pulling search results, video metadata, comments, and channel videos at scale.

Built from [hardened production code](#status) with real measurements at 1k / 10k / 100k scale.

## Features

- **4 crawler backends** with automatic fallback:
  - `YtdlpYouTubeCrawler` — primary path, no API key required (uses yt-dlp under the hood)
  - `VisibleYouTubeCrawler` — browser-based fallback (Playwright + scrapling)
  - `PlaywrightYouTubeCrawler` — thin compat wrapper over Visible
  - `YouTubeCrawler` — official Data API v3 client (requires key)
- **`BatchCollector`** — fan-out scheduler with:
  - Configurable concurrency (semaphore-bounded)
  - Checkpoint/resume (crash-safe)
  - Per-target timeout + isolation
  - Streaming write (one jsonl per target)
  - Optional shortfall retry for silent-short responses
- Four unified methods across all crawlers:
  - `search(keyword, limit)`
  - `get_post_detail(url)`
  - `get_comments(video_id, limit)`
  - `get_user_posts(channel, limit)`

## Quick start

```bash
git clone https://github.com/<you>/youtube-crawler.git
cd youtube-crawler
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium    # only if you'll use Visible/Playwright crawlers

python examples/quick_start.py
```

### Minimal example

```python
import asyncio
from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler

async def main():
    crawler = YtdlpYouTubeCrawler()
    comments = await crawler.get_comments("kJQP7kiw5Fk", limit=100)
    for c in comments[:3]:
        print(c.author, "-", c.content[:60])
    await crawler.close()

asyncio.run(main())
```

### Collecting at scale (10k / 100k comments)

```python
from pathlib import Path
from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler
from youtube_crawler.core.batch_collector import BatchCollector

crawler = YtdlpYouTubeCrawler()

async def fetch(video_id, limit):
    return await crawler.get_comments(video_id, limit=limit)

bc = BatchCollector(output_dir=Path("./data"), job_name="my-job")
result = await bc.run(
    targets=video_ids,                  # your list of video ids
    per_target_limit=1000,
    fetch=fetch,
    concurrency=4,                      # evidence says 4 is the sweet spot
    shortfall_retry_threshold=0.8,      # retry silent short responses
)
# Output: ./data/my-job/<video_id>.jsonl  (+ checkpoint.json)
```

See `examples/` for full runnable scripts, including the stress tests used to validate this package at 100k scale.

## Status

Real measurements from the scale tests in `examples/`:

| Scenario | Result |
|---|---|
| 1k baseline (search / comments / user_posts) | All pass on `YtdlpYouTubeCrawler` |
| 10k fan-out (10 videos × 1000 comments, serial) | 10000/10000 in 11 min |
| 10k fan-out (concurrent=4) | 9760/10000 in 3.5 min, 3.13× speedup |
| 100k stress (100 videos × 1000, concurrent=4) | 97/100 targets complete in 20 min, 63k comments collected |
| Memory at 100k | +148 MB RSS |

Known platform limits worth knowing before you scale:

- **Single-video comment ceiling**: YouTube hard-caps at ~7100 comments per video regardless of how you page. Go broader (more videos), not deeper.
- **Silent shortfall under concurrency**: ~40% of targets can return fewer comments than requested when YouTube's Innertube continuation ends early. `shortfall_retry_threshold=0.8` mitigates but doesn't eliminate — some videos simply don't have that many comments.
- **Visible.search limitation**: Scrapes the first page of results only (~32 items). Use `YtdlpYouTubeCrawler.search` for any real-scale search.

## Configuration

Edit `crawler_config.py` at the project root, or set environment variables (see `.env.example`). The API-based `YouTubeCrawler` requires `YOUTUBE_API_KEY`; the other three backends don't need any credentials.

## Project layout

```
youtube-crawler/
├── youtube_crawler/          # the package
│   ├── ytdlp_crawler.py      # primary crawler (no key)
│   ├── visible_crawler.py    # browser-based fallback
│   ├── playwright_crawler.py # compat shim → Visible
│   ├── crawler.py            # official Data API v3 client
│   ├── api_client.py         # low-level Data API helpers
│   ├── innertube_client.py   # Innertube private-API client
│   ├── ytdlp_client.py       # yt-dlp subprocess wrapper
│   ├── login.py              # cookie-based login helpers
│   ├── base.py               # BaseCrawler, CrawlResult, CommentResult
│   └── core/
│       ├── batch_collector.py
│       ├── browser_manager.py
│       ├── config.py
│       ├── exceptions.py
│       ├── proxy_manager.py
│       ├── rate_limiter.py
│       └── logger.py
├── examples/                 # runnable scale tests & demos
├── crawler_config.py         # user-editable high-level config
├── requirements.txt
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

Built on top of [yt-dlp](https://github.com/yt-dlp/yt-dlp), [scrapling](https://github.com/D4Vinci/Scrapling), and [Playwright](https://playwright.dev/).
