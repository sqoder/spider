"""
Concurrency verification for BatchCollector.

Fresh job_name "demo_concurrent", 3 videos × 300 comments, concurrency=3.
Goal: confirm parallel path is correctness-equivalent to the serial path
(all files written, checkpoint consistent, no duplicates, no lost targets).

Also prints elapsed vs the serial 73s baseline from demo_batch_collector.py
for the same workload — modest speedup expected since the shared rate
limiter still paces overall request rate.
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import shutil
from pathlib import Path

from youtube_crawler.core.batch_collector import BatchCollector
from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler


OUT = Path("/tmp/batch_collector_demo")
JOB = "demo_concurrent"
TARGETS = ["kJQP7kiw5Fk", "JGwWNGJdvx8", "9bZkp7q19f0"]
LIMIT = 300
CONCURRENCY = 3


async def main():
    job_dir = OUT / JOB
    if job_dir.exists():
        shutil.rmtree(job_dir)

    crawler = YtdlpYouTubeCrawler()

    async def fetch(target, limit):
        return await crawler.get_comments(target, limit=limit)

    print(f"=== concurrent run: {len(TARGETS)} targets, concurrency={CONCURRENCY} ===")
    bc = BatchCollector(output_dir=OUT, job_name=JOB)
    r = await bc.run(
        targets=TARGETS,
        per_target_limit=LIMIT,
        fetch=fetch,
        concurrency=CONCURRENCY,
    )

    print(f"\ncompleted={r.completed_targets} failed={r.failed_targets} "
          f"total_items={r.total_items} elapsed={r.elapsed_s}s "
          f"(serial baseline from earlier demo: 73.3s)")

    # Correctness assertions
    assert r.completed_targets == 3, f"expected 3 completed, got {r.completed_targets}"
    assert r.failed_targets == 0
    assert r.total_items >= 3 * LIMIT * 0.9

    # Every target file exists, non-empty, and its line count matches
    # the TargetResult.got — that's the real "no lost data" check.
    tr_by_target = {tr.target: tr for tr in r.per_target}
    for t in TARGETS:
        p = job_dir / f"{t}.jsonl"
        assert p.exists(), f"missing {p}"
        lines = p.read_text(encoding="utf-8").splitlines()
        assert lines, f"empty {p}"
        assert len(lines) == tr_by_target[t].got, (
            f"{t}: file has {len(lines)} lines but TargetResult.got={tr_by_target[t].got}"
        )

    # Checkpoint must list exactly the 3 targets as completed, none failed
    import json
    cp = json.loads((job_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert set(cp["completed"]) == set(TARGETS), f"checkpoint completed: {cp['completed']}"
    assert cp["failed"] == {}, f"unexpected failures in checkpoint: {cp['failed']}"

    # Idempotent resume: re-running the same job should skip everything.
    r2 = await bc.run(
        targets=TARGETS, per_target_limit=LIMIT, fetch=fetch, concurrency=CONCURRENCY
    )
    assert r2.skipped_targets == 3, f"expected 3 skipped on resume, got {r2.skipped_targets}"
    assert r2.completed_targets == 0

    await crawler.close()
    print("ALL CONCURRENCY ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
