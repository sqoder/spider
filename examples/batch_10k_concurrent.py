"""
10K concurrent via BatchCollector.

Same workload as fanout_10k.py (10 videos × 1000 comments) but routed through
BatchCollector(concurrency=4). Compares against the serial baseline from that
run (664s).

Goal: close the loop with one final evidence card — "can we stably hit 10k
across targets, concurrently, with checkpoint support".

Usage:
  python examples/batch_10k_concurrent.py
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import shutil
import time
from pathlib import Path

from youtube_crawler.core.batch_collector import BatchCollector
from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler


OUT = Path("/tmp/batch_10k")
JOB = "fanout10_c4"
TARGETS = [
    "kJQP7kiw5Fk",  # Despacito
    "JGwWNGJdvx8",  # Shape of You
    "RgKAFK5djSk",  # See You Again
    "9bZkp7q19f0",  # Gangnam Style
    "OPf0YbXqDm0",  # Uptown Funk
    "fRh_vgS2dFE",  # Sorry
    "YQHsXMglC9A",  # Hello
    "CevxZvSJLk8",  # Roar
    "hT_nvWreIhg",  # Counting Stars
    "papuvlVeZg8",  # Ocean Eyes
]
LIMIT = 1000
CONCURRENCY = 4

SERIAL_BASELINE_S = 664.0   # from fanout_10k.py


async def main():
    job_dir = OUT / JOB
    if job_dir.exists():
        shutil.rmtree(job_dir)

    crawler = YtdlpYouTubeCrawler()

    async def fetch(target, limit):
        return await crawler.get_comments(target, limit=limit)

    print(f"10K concurrent: {len(TARGETS)} videos × {LIMIT} comments, "
          f"concurrency={CONCURRENCY}")
    print(f"Serial baseline (from fanout_10k.py): {SERIAL_BASELINE_S}s")
    print()

    bc = BatchCollector(output_dir=OUT, job_name=JOB)
    t0 = time.time()
    r = await bc.run(
        targets=TARGETS,
        per_target_limit=LIMIT,
        fetch=fetch,
        concurrency=CONCURRENCY,
    )
    wall = time.time() - t0

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"  completed={r.completed_targets}/{len(TARGETS)}")
    print(f"  failed={r.failed_targets}")
    print(f"  total_items={r.total_items}")
    print(f"  elapsed={r.elapsed_s}s (wall {wall:.1f}s)")
    speedup = SERIAL_BASELINE_S / r.elapsed_s if r.elapsed_s else 0
    print(f"  speedup vs serial baseline: {speedup:.2f}×")

    # Per-target summary
    print("\n  per-target:")
    for tr in sorted(r.per_target, key=lambda x: x.target):
        status = "FAIL" if tr.error else f"{tr.got} items"
        print(f"    {tr.target}: {status} in {tr.elapsed_s}s"
              + (f" — {tr.error}" if tr.error else ""))

    # Sanity checks
    assert r.completed_targets == len(TARGETS), "not all targets completed"
    assert r.failed_targets == 0, "concurrent run hit failures"
    assert r.total_items >= len(TARGETS) * LIMIT * 0.95, (
        f"total items low: {r.total_items}"
    )

    # Verify every file exists and its line count matches TargetResult.got
    for tr in r.per_target:
        p = job_dir / f"{tr.target}.jsonl"
        lines = p.read_text(encoding="utf-8").splitlines()
        assert len(lines) == tr.got, f"{tr.target}: {len(lines)} lines vs got={tr.got}"
    print("\n  file-level integrity: OK")

    await crawler.close()
    print("\n10K CONCURRENT RUN: OK")


if __name__ == "__main__":
    asyncio.run(main())
