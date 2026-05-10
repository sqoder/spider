"""
Demo/verification for BatchCollector.

Runs 3 videos × 300 comments twice:
  Run 1: fresh — all 3 targets should be fetched
  Run 2: same job_name, same targets — all 3 should skip via checkpoint

Output dir: /tmp/batch_collector_demo/demo/
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
TARGETS = ["kJQP7kiw5Fk", "JGwWNGJdvx8", "9bZkp7q19f0"]
LIMIT = 300


async def main():
    # Clean slate for run 1
    if OUT.exists():
        shutil.rmtree(OUT)

    crawler = YtdlpYouTubeCrawler()

    async def fetch(target, limit):
        return await crawler.get_comments(target, limit=limit)

    # ---- Run 1: fresh ----
    print("=" * 50)
    print("RUN 1 (fresh)")
    print("=" * 50)
    bc = BatchCollector(output_dir=OUT, job_name="demo")
    r1 = await bc.run(targets=TARGETS, per_target_limit=LIMIT, fetch=fetch)

    print(f"\nrun1: completed={r1.completed_targets} skipped={r1.skipped_targets} "
          f"failed={r1.failed_targets} total_items={r1.total_items} "
          f"elapsed={r1.elapsed_s}s")

    assert r1.completed_targets == 3, f"expected 3 completed, got {r1.completed_targets}"
    assert r1.skipped_targets == 0, f"expected 0 skipped, got {r1.skipped_targets}"
    assert r1.total_items >= 3 * LIMIT * 0.9, f"too few items: {r1.total_items}"

    # Verify per-target files exist and have content
    for t in TARGETS:
        p = OUT / "demo" / f"{t}.jsonl"
        assert p.exists(), f"missing {p}"
        lines = p.read_text(encoding="utf-8").splitlines()
        assert len(lines) > 0, f"empty {p}"
    print("run 1 assertions: OK")

    # ---- Run 2: should skip everything via checkpoint ----
    print("\n" + "=" * 50)
    print("RUN 2 (checkpoint resume)")
    print("=" * 50)
    bc2 = BatchCollector(output_dir=OUT, job_name="demo")
    r2 = await bc2.run(targets=TARGETS, per_target_limit=LIMIT, fetch=fetch)

    print(f"\nrun2: completed={r2.completed_targets} skipped={r2.skipped_targets} "
          f"failed={r2.failed_targets} elapsed={r2.elapsed_s}s")

    assert r2.skipped_targets == 3, f"expected 3 skipped, got {r2.skipped_targets}"
    assert r2.completed_targets == 0, f"expected 0 completed, got {r2.completed_targets}"
    assert r2.elapsed_s < 5, f"run 2 should be near-instant, took {r2.elapsed_s}s"
    print("run 2 assertions: OK")

    # ---- Run 3: partial reset — delete one target's jsonl AND its entry in
    # checkpoint.completed. Verify just that one is refetched. ----
    print("\n" + "=" * 50)
    print("RUN 3 (partial resume — 1 target redone)")
    print("=" * 50)
    import json
    cp = OUT / "demo" / "checkpoint.json"
    state = json.loads(cp.read_text(encoding="utf-8"))
    state["completed"].remove(TARGETS[1])
    cp.write_text(json.dumps(state, indent=2), encoding="utf-8")

    bc3 = BatchCollector(output_dir=OUT, job_name="demo")
    r3 = await bc3.run(targets=TARGETS, per_target_limit=LIMIT, fetch=fetch)

    print(f"\nrun3: completed={r3.completed_targets} skipped={r3.skipped_targets} "
          f"failed={r3.failed_targets} elapsed={r3.elapsed_s}s")

    assert r3.completed_targets == 1, f"expected 1 completed, got {r3.completed_targets}"
    assert r3.skipped_targets == 2, f"expected 2 skipped, got {r3.skipped_targets}"
    print("run 3 assertions: OK")

    await crawler.close()
    print("\nALL DEMO ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
