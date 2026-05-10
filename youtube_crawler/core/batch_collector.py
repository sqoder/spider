"""
Fan-out batch collector.

Takes a list of target ids and a fetch callable, runs them with configurable
concurrency, writes one jsonl per target, persists progress in a checkpoint
file so the job can resume from where it crashed.

Does NOT add general retries or rate limiting — the underlying crawler
already handles transient errors and the crawler's own rate limiter keeps
pacing correct. The only optional retry is `shortfall_retry_threshold`,
which re-fetches a target when it returned suspiciously few items without
an error (the "silent shortfall" pattern seen under concurrent YouTube
Innertube load).

Typical usage:

    from youtube_crawler.core.batch_collector import BatchCollector
    from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler

    crawler = YtdlpYouTubeCrawler()

    async def fetch(target, limit):
        return await crawler.get_comments(target, limit=limit)

    collector = BatchCollector(output_dir=Path("/tmp/jobs"), job_name="demo")
    result = await collector.run(
        targets=["kJQP7kiw5Fk", "JGwWNGJdvx8"],
        per_target_limit=1000,
        fetch=fetch,
        concurrency=4,
        shortfall_retry_threshold=0.8,   # retry once if got < 80% of limit
    )
    print(result)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger


FetchFn = Callable[[str, int], Awaitable[list[Any]]]


@dataclass
class TargetResult:
    target: str
    got: int = 0
    elapsed_s: float = 0.0
    error: str | None = None
    retries: int = 0           # how many times fetch() was invoked (1 = no retry)


@dataclass
class BatchResult:
    job_name: str
    total_targets: int
    completed_targets: int = 0
    skipped_targets: int = 0          # already done via checkpoint
    failed_targets: int = 0
    total_items: int = 0
    elapsed_s: float = 0.0
    per_target: list[TargetResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "per_target"},
            "per_target": [asdict(r) for r in self.per_target],
        }


def _serialize(obj: Any) -> dict:
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


class BatchCollector:
    """Serial fan-out runner with checkpoint + per-target isolation."""

    def __init__(self, output_dir: Path, job_name: str):
        self.job_dir = Path(output_dir) / job_name
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.job_name = job_name
        self.checkpoint_path = self.job_dir / "checkpoint.json"
        self._ckpt_lock = asyncio.Lock()

    # ---- checkpoint ----

    def _load_checkpoint(self) -> dict:
        if self.checkpoint_path.exists():
            try:
                return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning(
                    f"[BatchCollector] checkpoint {self.checkpoint_path} is corrupt, "
                    "starting fresh"
                )
        return {"completed": [], "failed": {}}

    def _save_checkpoint(self, state: dict) -> None:
        tmp = self.checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.checkpoint_path)

    # ---- core ----

    async def run(
        self,
        targets: list[str],
        per_target_limit: int,
        fetch: FetchFn,
        per_target_timeout: float = 600.0,
        concurrency: int = 1,
        shortfall_retry_threshold: float | None = None,
    ) -> BatchResult:
        """Fan out a list of targets through `fetch`, writing one jsonl per target.

        Args:
            targets: list of target ids to fetch.
            per_target_limit: passed through as the `limit` arg to fetch().
            fetch: async callable `(target, limit) -> list[item]`.
            per_target_timeout: per-target hard timeout in seconds.
            concurrency: number of concurrent in-flight fetches. 1 = serial.
            shortfall_retry_threshold: if set to e.g. 0.8, any target that returns
                fewer than (threshold × per_target_limit) items — without an error —
                is retried once. Useful for the "silent shortfall" pattern where
                YouTube's Innertube continuation ends early under concurrent load.
                None (default) disables retry; the first result is kept as-is.
        """
        if concurrency < 1:
            raise ValueError(f"concurrency must be >= 1, got {concurrency}")
        if shortfall_retry_threshold is not None and not 0 < shortfall_retry_threshold <= 1:
            raise ValueError(
                f"shortfall_retry_threshold must be in (0, 1], got {shortfall_retry_threshold}"
            )

        state = self._load_checkpoint()
        completed: set[str] = set(state.get("completed", []))
        failed: dict[str, str] = dict(state.get("failed", {}))

        result = BatchResult(job_name=self.job_name, total_targets=len(targets))
        t_start = time.time()

        pending = [t for t in targets if t not in completed]
        result.skipped_targets = len(targets) - len(pending)
        for t in targets:
            if t in completed:
                logger.info(f"[{self.job_name}] skip (checkpoint): {t}")

        if concurrency == 1:
            # Serial path — preserves original log ordering.
            for i, target in enumerate(pending, 1):
                logger.info(f"[{self.job_name}] ({i}/{len(pending)}) fetching: {target}")
                tr = await self._run_one(
                    target, per_target_limit, fetch, per_target_timeout,
                    shortfall_retry_threshold,
                )
                await self._record(tr, result, completed, failed)
        else:
            # Parallel path — semaphore bounds in-flight fetches.
            sem = asyncio.Semaphore(concurrency)
            logger.info(
                f"[{self.job_name}] running {len(pending)} targets "
                f"with concurrency={concurrency}"
            )

            async def worker(idx: int, target: str) -> TargetResult:
                async with sem:
                    logger.info(
                        f"[{self.job_name}] ({idx}/{len(pending)}) fetching: {target}"
                    )
                    tr = await self._run_one(
                        target, per_target_limit, fetch, per_target_timeout,
                        shortfall_retry_threshold,
                    )
                    await self._record(tr, result, completed, failed)
                    return tr

            await asyncio.gather(
                *(worker(i, t) for i, t in enumerate(pending, 1))
            )

        result.elapsed_s = round(time.time() - t_start, 1)
        return result

    async def _record(
        self,
        tr: TargetResult,
        result: BatchResult,
        completed: set[str],
        failed: dict[str, str],
    ) -> None:
        """Apply one target's outcome to shared state and persist checkpoint.

        Holds _ckpt_lock so concurrent workers don't interleave checkpoint writes
        or corrupt the BatchResult counters.
        """
        async with self._ckpt_lock:
            result.per_target.append(tr)
            if tr.error:
                result.failed_targets += 1
                failed[tr.target] = tr.error
            else:
                result.completed_targets += 1
                result.total_items += tr.got
                completed.add(tr.target)
                failed.pop(tr.target, None)

            self._save_checkpoint({
                "completed": sorted(completed),
                "failed": failed,
            })

    async def _run_one(
        self,
        target: str,
        limit: int,
        fetch: FetchFn,
        timeout: float,
        shortfall_retry_threshold: float | None = None,
    ) -> TargetResult:
        out_path = self.job_dir / f"{target}.jsonl"

        async def _attempt() -> tuple[list | None, float, str | None]:
            t0 = time.time()
            try:
                items = await asyncio.wait_for(fetch(target, limit), timeout=timeout)
                return items, time.time() - t0, None
            except asyncio.TimeoutError:
                return None, time.time() - t0, f"TimeoutError: exceeded {timeout}s"
            except Exception as e:
                return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:300]}"

        items, elapsed, err = await _attempt()
        retries = 1

        # Shortfall retry: the fetch succeeded but returned fewer items than expected.
        # Typical cause: Innertube continuation ended early under concurrent load.
        # We do NOT retry on errors — those already mean per-target isolation kicked in
        # and the caller gets a clean failure record.
        if (
            err is None
            and items is not None
            and shortfall_retry_threshold is not None
            and len(items) < limit * shortfall_retry_threshold
        ):
            first_got = len(items)
            logger.info(
                f"[{self.job_name}] shortfall on {target}: got {first_got}/{limit} "
                f"(<{shortfall_retry_threshold:.0%}), retrying once"
            )
            retry_items, retry_elapsed, retry_err = await _attempt()
            retries = 2
            elapsed += retry_elapsed
            # Keep whichever attempt produced more items (retry may fail or do worse).
            if retry_err is None and retry_items is not None and len(retry_items) > first_got:
                logger.info(
                    f"[{self.job_name}] retry on {target} improved: "
                    f"{first_got} → {len(retry_items)}"
                )
                items = retry_items
            else:
                logger.info(
                    f"[{self.job_name}] retry on {target} did not improve "
                    f"(kept first result: {first_got} items)"
                )

        if err is not None or items is None:
            return TargetResult(
                target=target,
                elapsed_s=round(elapsed, 1),
                error=err or "unknown error",
                retries=retries,
            )

        # Stream: write as we go so a crash mid-serialize doesn't lose the lot.
        # File is overwritten fully on success — no resume-mid-file semantics.
        with out_path.open("w", encoding="utf-8") as f:
            for item in items:
                try:
                    f.write(json.dumps(_serialize(item), ensure_ascii=False, default=str))
                except Exception as e:
                    f.write(json.dumps({"_serialize_error": str(e)}))
                f.write("\n")

        return TargetResult(
            target=target,
            got=len(items),
            elapsed_s=round(elapsed, 1),
            retries=retries,
        )
