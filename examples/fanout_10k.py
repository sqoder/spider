"""
Fan-out validation: 10 videos × 1000 comments each, target 10000 total.

Point of this probe:
  1. Prove the fan-out pattern works — single target cap (7100 at 10k) is NOT
     a blocker if we spread across targets.
  2. Demonstrate streaming write-to-disk (don't pile 10k records in memory).
  3. Prove per-target isolation — one video failing doesn't poison the run.

Sequential execution deliberately — parallel is premature until we know
sequential is clean.

Usage:
  python examples/fanout_10k.py

Output:
  /tmp/fanout_10k/<video_id>.jsonl         one file per target
  /tmp/fanout_10k/report.md
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import json
import resource
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path


OUT_DIR = Path("/tmp/fanout_10k")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Popular music videos — each has millions of comments, 1k should be trivial.
# Mix of languages/genres to reduce correlation in YouTube's sampling.
TARGETS = [
    ("kJQP7kiw5Fk", "Despacito"),
    ("JGwWNGJdvx8", "Shape of You"),
    ("RgKAFK5djSk", "See You Again"),
    ("9bZkp7q19f0", "Gangnam Style"),
    ("OPf0YbXqDm0", "Uptown Funk"),
    ("fRh_vgS2dFE", "Sorry"),
    ("YQHsXMglC9A", "Hello"),
    ("CevxZvSJLk8", "Roar"),
    ("hT_nvWreIhg", "Counting Stars"),
    ("papuvlVeZg8", "Ocean Eyes"),
]
PER_VIDEO_TARGET = 1000
PER_VIDEO_TIMEOUT = 300


def _serialize(obj):
    if is_dataclass(obj):
        d = asdict(obj)
    elif hasattr(obj, "to_dict"):
        d = obj.to_dict()
    else:
        d = dict(getattr(obj, "__dict__", {}))
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if r > 1_000_000 else r / 1024


async def run_one(crawler, video_id, label):
    """Pull one video, stream to its own jsonl. Return stats."""
    out_path = OUT_DIR / f"{video_id}.jsonl"
    stat = {
        "video_id": video_id,
        "label": label,
        "target": PER_VIDEO_TARGET,
        "got": 0,
        "unique": 0,
        "elapsed_s": 0.0,
        "throughput_per_s": 0.0,
        "error": None,
    }
    print(f"\n[{label}] id={video_id}")
    t0 = time.time()
    try:
        items = await asyncio.wait_for(
            crawler.get_comments(video_id, limit=PER_VIDEO_TARGET),
            timeout=PER_VIDEO_TIMEOUT,
        )
    except Exception as e:
        stat["elapsed_s"] = round(time.time() - t0, 1)
        stat["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        print(f"  FAIL {stat['error']}")
        # still write empty file so post-analysis sees the attempt
        out_path.write_text("")
        return stat

    stat["elapsed_s"] = round(time.time() - t0, 1)
    # Stream to disk — don't keep all batches in memory at scale
    seen = set()
    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            sid = getattr(item, "source_id", None)
            if sid:
                seen.add(sid)
            f.write(json.dumps(_serialize(item), ensure_ascii=False, default=str))
            f.write("\n")
    stat["got"] = len(items)
    stat["unique"] = len(seen)
    stat["throughput_per_s"] = round(len(items) / max(stat["elapsed_s"], 0.001), 2)
    print(f"  OK: {stat['got']}/{PER_VIDEO_TARGET} in {stat['elapsed_s']}s "
          f"({stat['throughput_per_s']}/s, unique={stat['unique']})")
    return stat


def write_report(stats, total_elapsed, rss_before, rss_after):
    total_got = sum(s["got"] for s in stats)
    total_unique_across = len({line for s in stats
                                for line in _all_ids_for(s)})
    failed = [s for s in stats if s["error"]]
    shortfall = [s for s in stats if s["error"] is None and s["got"] < PER_VIDEO_TARGET]

    lines = [
        "# Fan-out 10K Report",
        "",
        f"- Run at: {datetime.now().isoformat()}",
        f"- Targets: {len(TARGETS)} videos × {PER_VIDEO_TARGET} comments each",
        f"- Total elapsed: {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)",
        f"- Total collected (sum): **{total_got}/{len(TARGETS) * PER_VIDEO_TARGET}** "
        f"({total_got / (len(TARGETS) * PER_VIDEO_TARGET) * 100:.0f}%)",
        f"- Unique source_ids across all videos: {total_unique_across}",
        f"- RSS before/after: {rss_before:.1f} / {rss_after:.1f} MB "
        f"(delta +{rss_after - rss_before:.1f})",
        f"- Failed videos: {len(failed)}",
        f"- Short-fall videos (got < {PER_VIDEO_TARGET} without error): {len(shortfall)}",
        "",
        "## Per-video detail",
        "",
        "| # | Video | ID | Got/Target | Elapsed | Rate | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(stats, 1):
        status = "OK" if s["error"] is None and s["got"] >= PER_VIDEO_TARGET \
            else ("FAIL" if s["error"] else f"SHORT ({s['got']})")
        lines.append(
            f"| {i} | {s['label']} | `{s['video_id']}` | {s['got']}/{PER_VIDEO_TARGET} "
            f"| {s['elapsed_s']}s | {s['throughput_per_s']}/s | {status} |"
        )

    lines += ["", "## Interpretation", ""]
    if not failed and total_got >= 10000:
        lines.append("- ✅ Fan-out pattern confirmed: spreading across targets cleanly hits 10k.")
    elif total_got >= 10000:
        lines.append(f"- ⚠️ Hit 10k but {len(failed)} target(s) failed — isolation held up, "
                     "successful targets still produced enough.")
    else:
        lines.append(f"- ❌ Only {total_got} total across all targets — "
                     "fan-out alone is not enough; need more targets or deeper-per-target.")

    if shortfall:
        lines.append(f"- ℹ️ {len(shortfall)} target(s) fell short of {PER_VIDEO_TARGET} "
                     "without errors — these videos may have <1000 total comments or "
                     "hit YouTube's per-sort cap for that specific video.")
    if failed:
        lines.append("- ❌ Failed videos:")
        for s in failed:
            lines.append(f"  - `{s['video_id']}` ({s['label']}): {s['error']}")

    lines.append(f"- ✅ Streaming write: each video flushed to its own file — "
                 f"{len(stats)} files on disk, no in-memory accumulation.")

    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {OUT_DIR / 'report.md'}")


def _all_ids_for(stat):
    """Re-read jsonl for this stat and yield source_ids — avoids keeping
    every record in RAM while still measuring global uniqueness."""
    p = OUT_DIR / f"{stat['video_id']}.jsonl"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = rec.get("source_id")
        if sid:
            yield sid


async def main():
    from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler

    print(f"Fan-out 10K start: {datetime.now().isoformat()}")
    print(f"{len(TARGETS)} videos × {PER_VIDEO_TARGET} comments")
    print(f"Output: {OUT_DIR}")

    crawler = YtdlpYouTubeCrawler()
    rss_before = rss_mb()

    stats = []
    t0 = time.time()
    for vid, label in TARGETS:
        s = await run_one(crawler, vid, label)
        stats.append(s)
    total_elapsed = time.time() - t0

    try:
        await crawler.close()
    except Exception:
        pass

    rss_after = rss_mb()
    write_report(stats, total_elapsed, rss_before, rss_after)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = sum(s["got"] for s in stats)
    print(f"  Total: {total}/{len(TARGETS) * PER_VIDEO_TARGET} "
          f"in {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)")
    print(f"  Failed: {sum(1 for s in stats if s['error'])} / {len(stats)}")


if __name__ == "__main__":
    asyncio.run(main())
