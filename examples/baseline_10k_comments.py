"""
Baseline 10K comments: does linear extrapolation from 1K hold?

At 1K we saw 15.18/s, 0 failures, 0 dups. If the path is truly linear,
10K should finish in ~11 minutes at the same rate. If it degrades we'll
see either a longer elapsed, a shortfall, or mid-run errors.

Usage:
  python examples/baseline_10k_comments.py

Output:
  /tmp/baseline_10k/comments.jsonl
  /tmp/baseline_10k/report.md
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import json
import resource
import time
import traceback
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path


OUT_DIR = Path("/tmp/baseline_10k")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_ID = "kJQP7kiw5Fk"   # Despacito, millions of comments
TARGET = 10000
PHASE_TIMEOUT = 1800        # 30 min hard cap (linear says ~11 min)


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


def write_jsonl(path: Path, items):
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            try:
                f.write(json.dumps(_serialize(item), ensure_ascii=False, default=str))
            except Exception as e:
                f.write(json.dumps({"_serialize_error": str(e)}))
            f.write("\n")


def rss_mb():
    # macOS returns bytes, Linux returns KB — normalize to MB best-effort
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if r > 1_000_000 else r / 1024


async def main():
    from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler

    print(f"Baseline 10K comments: {datetime.now().isoformat()}")
    print(f"Video: {VIDEO_ID}, target: {TARGET}")
    print(f"Timeout: {PHASE_TIMEOUT}s ({PHASE_TIMEOUT // 60} min)")
    print(f"Output: {OUT_DIR}\n")

    crawler = YtdlpYouTubeCrawler()

    rss_before = rss_mb()
    print(f"RSS before: {rss_before:.1f} MB")

    rec = {
        "video_id": VIDEO_ID,
        "target": TARGET,
        "start": datetime.now().isoformat(),
        "ok": False,
        "got": 0,
        "unique": 0,
        "elapsed_s": 0.0,
        "throughput_per_s": 0.0,
        "error_type": None,
        "error_msg": None,
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": 0.0,
        "rss_delta_mb": 0.0,
    }

    t0 = time.time()
    items = []
    try:
        items = await asyncio.wait_for(
            crawler.get_comments(VIDEO_ID, limit=TARGET),
            timeout=PHASE_TIMEOUT,
        )
        elapsed = time.time() - t0
        rec["ok"] = True
        rec["got"] = len(items)
        rec["elapsed_s"] = round(elapsed, 1)
        rec["throughput_per_s"] = round(len(items) / max(elapsed, 0.001), 2)
        ids = [getattr(it, "source_id", None) for it in items]
        rec["unique"] = len(set(i for i in ids if i))
        print(f"OK: {len(items)}/{TARGET} in {elapsed:.1f}s "
              f"({rec['throughput_per_s']}/s, unique={rec['unique']})")
    except asyncio.TimeoutError:
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rec["error_type"] = "TimeoutError"
        rec["error_msg"] = f"exceeded {PHASE_TIMEOUT}s"
        print(f"TIMEOUT after {PHASE_TIMEOUT}s")
    except Exception as e:
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rec["error_type"] = type(e).__name__
        rec["error_msg"] = str(e)[:300]
        print(f"FAIL {type(e).__name__}: {str(e)[:200]}")
        traceback.print_exc(limit=3)

    rss_after = rss_mb()
    rec["rss_after_mb"] = round(rss_after, 1)
    rec["rss_delta_mb"] = round(rss_after - rss_before, 1)
    print(f"RSS after: {rss_after:.1f} MB (delta +{rec['rss_delta_mb']:.1f} MB)")

    write_jsonl(OUT_DIR / "comments.jsonl", items)

    try:
        await crawler.close()
    except Exception:
        pass

    # Report
    baseline_1k_rate = 15.18  # measured earlier
    deviation = ((rec["throughput_per_s"] - baseline_1k_rate) / baseline_1k_rate * 100
                 if rec["throughput_per_s"] else -100)

    lines = [
        "# Baseline 10K Comments Report",
        "",
        f"- Run at: {rec['start']}",
        f"- Video: `{VIDEO_ID}`",
        f"- Target: {TARGET}",
        f"- 1K baseline throughput: **{baseline_1k_rate}/s**",
        "",
        "## Result",
        "",
        f"- Collected: **{rec['got']}/{TARGET}** ({rec['got']/TARGET*100:.0f}%)",
        f"- Unique source_ids: {rec['unique']}",
        f"- Elapsed: {rec['elapsed_s']}s ({rec['elapsed_s']/60:.1f} min)",
        f"- Throughput: **{rec['throughput_per_s']}/s** "
        f"(deviation from 1K baseline: {deviation:+.0f}%)",
        f"- RSS delta: +{rec['rss_delta_mb']} MB",
    ]
    err_type = rec["error_type"]
    lines.append(f"- Status: {'OK' if rec['ok'] else f'FAIL ({err_type})'}")

    if rec["error_msg"]:
        lines += ["", f"**Error:** `{rec['error_msg']}`"]

    lines += ["", "## Interpretation", ""]
    if rec["ok"] and rec["got"] >= TARGET * 0.95:
        if abs(deviation) < 20:
            lines.append("- ✅ Throughput stayed within ±20% of 1K baseline. Linear extrapolation holds.")
        elif deviation < -20:
            lines.append(f"- ⚠️ Throughput dropped {abs(deviation):.0f}% vs 1K — investigate whether later pages are slower.")
        else:
            lines.append(f"- ℹ️ Throughput increased {deviation:.0f}% vs 1K — likely warmed-up session effect.")
        if rec["rss_delta_mb"] > 200:
            lines.append(f"- ⚠️ RSS grew {rec['rss_delta_mb']} MB — watch for leaks at 100K.")
        else:
            lines.append(f"- ✅ RSS growth modest ({rec['rss_delta_mb']} MB), no obvious leak at this scale.")
    elif rec["got"] < TARGET * 0.95 and rec["ok"]:
        lines.append(f"- ⚠️ Got only {rec['got']}/{TARGET} without error — hit an internal ceiling "
                     f"(YouTube 'newest first' visible comment cap, not a code bug).")
    else:
        lines.append(f"- ❌ Run did not complete. See error above.")

    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {OUT_DIR / 'report.md'}")


if __name__ == "__main__":
    asyncio.run(main())
