"""
Unit test for BatchCollector.shortfall_retry_threshold.

Uses a fake fetch() that returns controlled short/full payloads — no network,
no crawler, runs in under a second. Covers:

  1. No threshold set (default): short results kept, no retry.
  2. Threshold set, shortfall on first attempt, retry returns full: we keep the retry.
  3. Threshold set, shortfall on first, retry returns even less: we keep the first.
  4. Threshold set, first attempt errors: no retry (error-path unchanged).

Run:
  python examples/test_shortfall_retry.py
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

from youtube_crawler.core.batch_collector import BatchCollector


OUT = Path("/tmp/shortfall_retry_test")


def make_item(i):
    # Minimal object with source_id and content; BatchCollector will serialize it.
    return SimpleNamespace(source_id=f"id{i}", content=f"item {i}")


class FakeFetcher:
    """Records calls per target, returns configurable payloads in sequence."""

    def __init__(self, per_target_payloads):
        # per_target_payloads: dict[target] -> list of payloads (one per attempt).
        # A payload is either an int (items to return) or an Exception to raise.
        self.payloads = per_target_payloads
        self.calls = {t: 0 for t in per_target_payloads}

    async def fetch(self, target, limit):
        idx = self.calls[target]
        self.calls[target] += 1
        payload = self.payloads[target][idx]
        if isinstance(payload, BaseException):
            raise payload
        return [make_item(i) for i in range(payload)]


async def test_case(name, payloads, threshold, expected):
    """expected: dict with keys got, retries, error(bool)"""
    if OUT.exists():
        shutil.rmtree(OUT)
    fetcher = FakeFetcher(payloads)
    bc = BatchCollector(output_dir=OUT, job_name=name)
    r = await bc.run(
        targets=list(payloads.keys()),
        per_target_limit=1000,
        fetch=fetcher.fetch,
        per_target_timeout=5,
        shortfall_retry_threshold=threshold,
    )
    tr = r.per_target[0]
    got = tr.got
    retries = tr.retries
    error = tr.error is not None

    ok = (
        got == expected["got"]
        and retries == expected["retries"]
        and error == expected["error"]
    )
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {name}: got={got} retries={retries} error={error}  "
          f"(expected {expected})")
    return ok


async def main():
    all_ok = True

    # 1. No threshold — keep whatever first attempt returns.
    all_ok &= await test_case(
        "no_threshold",
        {"A": [500]},
        threshold=None,
        expected={"got": 500, "retries": 1, "error": False},
    )

    # 2. Threshold 0.8, first short, retry full — keep retry.
    all_ok &= await test_case(
        "retry_improves",
        {"A": [400, 950]},
        threshold=0.8,
        expected={"got": 950, "retries": 2, "error": False},
    )

    # 3. Threshold 0.8, first short, retry even shorter — keep first.
    all_ok &= await test_case(
        "retry_worse",
        {"A": [500, 300]},
        threshold=0.8,
        expected={"got": 500, "retries": 2, "error": False},
    )

    # 4. First attempt raises — no retry, error recorded (shortfall retry is
    #    for silent shortfalls only, not for exceptions).
    all_ok &= await test_case(
        "error_no_retry",
        {"A": [RuntimeError("boom")]},
        threshold=0.8,
        expected={"got": 0, "retries": 1, "error": True},
    )

    # 5. Threshold set, first attempt already hits limit — no retry.
    all_ok &= await test_case(
        "full_no_retry",
        {"A": [1000]},
        threshold=0.8,
        expected={"got": 1000, "retries": 1, "error": False},
    )

    print()
    if all_ok:
        print("ALL SHORTFALL-RETRY TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
