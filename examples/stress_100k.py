"""
100K real stress test.

Protocol:
  1. Search to obtain 100 real video IDs (realistic production pattern:
     discover targets via search → fan-out comments).
  2. BatchCollector(concurrency=4) runs 100 targets × 1000 comments each.
  3. Report: completion rate, total items, shortfall distribution,
     memory growth, wall time.

Not expected to collect exactly 100000 comments — search results always
include cold videos with <1000 available comments. The point is to prove
stability, not to hit an arbitrary number.

Usage:
  python examples/stress_100k.py

Output:
  /tmp/batch_100k/production/<video_id>.jsonl  (up to 100 files)
  /tmp/batch_100k/production/checkpoint.json
  /tmp/batch_100k/stress_report.md
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import json
import resource
import shutil
import time
from pathlib import Path

from youtube_crawler.core.batch_collector import BatchCollector
from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler


OUT = Path("/tmp/batch_100k")
JOB = "production"
KEYWORD = "music video"
NUM_VIDEOS = 100
PER_VIDEO_LIMIT = 1000
CONCURRENCY = 4
PER_TARGET_TIMEOUT = 600

# Evidence-based references
EXPECTED_MIN_COMPLETION = 0.95       # targets completing (no exception)
EXPECTED_MIN_DATA_RATE = 0.60        # avg got/limit across targets (realistic — many cold videos)


def rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if r > 1_000_000 else r / 1024


async def discover_targets(crawler) -> list[str]:
    print(f"[discover] search({KEYWORD!r}, limit={NUM_VIDEOS})")
    t0 = time.time()
    items = await crawler.search(KEYWORD, limit=NUM_VIDEOS)
    elapsed = time.time() - t0
    ids = [i.source_id for i in items if getattr(i, "source_id", None)]
    # dedup, preserve order
    seen = set()
    unique = []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            unique.append(vid)
    print(f"[discover] got {len(unique)} unique ids in {elapsed:.1f}s")
    if len(unique) < NUM_VIDEOS * 0.5:
        raise RuntimeError(f"too few ids from search: {len(unique)}")
    return unique[:NUM_VIDEOS]


def write_report(out_path: Path, targets: list[str], r, wall_s: float,
                  rss_start: float, rss_end: float, discover_elapsed: float):
    got_by_target = {tr.target: tr.got for tr in r.per_target}
    err_by_target = {tr.target: tr.error for tr in r.per_target if tr.error}

    # shortfall analysis
    shortfall_80 = [t for t, g in got_by_target.items() if g < PER_VIDEO_LIMIT * 0.8 and t not in err_by_target]
    hit_limit = [t for t, g in got_by_target.items() if g >= PER_VIDEO_LIMIT]
    partial = [t for t, g in got_by_target.items() if 0 < g < PER_VIDEO_LIMIT]
    zero = [t for t, g in got_by_target.items() if g == 0 and t not in err_by_target]

    total_items = r.total_items
    avg_rate = total_items / (len(targets) * PER_VIDEO_LIMIT) if targets else 0

    lines = [
        "# 100K Stress Test Report",
        "",
        f"- Targets: {len(targets)} videos × {PER_VIDEO_LIMIT} comments",
        f"- Concurrency: {CONCURRENCY}",
        f"- Discover (search) elapsed: {discover_elapsed:.1f}s",
        f"- Fetch wall time: {wall_s:.1f}s ({wall_s/60:.1f} min)",
        f"- RSS: {rss_start:.0f} MB → {rss_end:.0f} MB (Δ+{rss_end - rss_start:.0f})",
        "",
        "## Headline",
        "",
        f"- **Completed targets**: {r.completed_targets}/{len(targets)} "
        f"({r.completed_targets / len(targets) * 100:.1f}%)",
        f"- **Failed targets**: {r.failed_targets}",
        f"- **Total items collected**: {total_items} / {len(targets) * PER_VIDEO_LIMIT} "
        f"({avg_rate * 100:.1f}% of theoretical max)",
        "",
        "## Distribution",
        "",
        f"- Targets hitting full limit ({PER_VIDEO_LIMIT}+): {len(hit_limit)}",
        f"- Targets with partial data (1 to {PER_VIDEO_LIMIT - 1}): {len(partial)}",
        f"- Targets with shortfall (<80%): {len(shortfall_80)}",
        f"- Targets with zero items but no error: {len(zero)}",
        f"- Targets failed with exception: {r.failed_targets}",
        "",
    ]

    if err_by_target:
        lines.append("## Failure detail")
        lines.append("")
        for t, err in list(err_by_target.items())[:20]:
            lines.append(f"- `{t}`: {err}")
        if len(err_by_target) > 20:
            lines.append(f"- … and {len(err_by_target) - 20} more")
        lines.append("")

    lines.append("## Verdict")
    lines.append("")
    completion_rate = r.completed_targets / len(targets)
    if completion_rate >= EXPECTED_MIN_COMPLETION and avg_rate >= EXPECTED_MIN_DATA_RATE:
        lines.append(f"- ✅ Stable at 100-target scale. "
                     f"{completion_rate*100:.0f}% targets completed, "
                     f"{avg_rate*100:.0f}% of theoretical max data collected.")
    else:
        lines.append(f"- ⚠️ Stability concerns: "
                     f"{completion_rate*100:.0f}% targets completed (expected ≥{EXPECTED_MIN_COMPLETION*100:.0f}%), "
                     f"{avg_rate*100:.0f}% data rate (expected ≥{EXPECTED_MIN_DATA_RATE*100:.0f}%).")

    if r.failed_targets == 0:
        lines.append("- ✅ Zero hard failures — error isolation and retry worked.")
    if rss_end - rss_start < 3000:
        lines.append(f"- ✅ Memory growth ({rss_end - rss_start:.0f} MB) within reason for this scale.")
    else:
        lines.append(f"- ⚠️ Memory grew {rss_end - rss_start:.0f} MB — watch for leaks at 1M scale.")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {out_path}")


async def main():
    # Clean slate; if interrupted mid-run, comment this out to resume via checkpoint.
    job_dir = OUT / JOB
    if job_dir.exists():
        shutil.rmtree(job_dir)

    crawler = YtdlpYouTubeCrawler()

    # Phase 1: discover
    t_disc = time.time()
    targets = await discover_targets(crawler)
    discover_elapsed = time.time() - t_disc

    # Phase 2: fan-out
    print(f"\n[fetch] {len(targets)} targets, concurrency={CONCURRENCY}, "
          f"per-target timeout {PER_TARGET_TIMEOUT}s")
    rss_start = rss_mb()
    print(f"[fetch] RSS start: {rss_start:.0f} MB")

    async def fetch(target, limit):
        return await crawler.get_comments(target, limit=limit)

    bc = BatchCollector(output_dir=OUT, job_name=JOB)
    t0 = time.time()
    r = await bc.run(
        targets=targets,
        per_target_limit=PER_VIDEO_LIMIT,
        fetch=fetch,
        per_target_timeout=PER_TARGET_TIMEOUT,
        concurrency=CONCURRENCY,
    )
    wall = time.time() - t0
    rss_end = rss_mb()

    try:
        await crawler.close()
    except Exception:
        pass

    # Phase 3: report
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"  completed: {r.completed_targets}/{len(targets)}")
    print(f"  failed:    {r.failed_targets}")
    print(f"  items:     {r.total_items}")
    print(f"  wall:      {wall:.0f}s ({wall/60:.1f} min)")
    print(f"  RSS delta: +{rss_end - rss_start:.0f} MB")

    write_report(OUT / "stress_report.md", targets, r, wall,
                  rss_start, rss_end, discover_elapsed)


if __name__ == "__main__":
    asyncio.run(main())
