"""
Baseline probe: run 3 representative YouTube workloads at 500-1000 scale
using the yt-dlp crawler (our designated main workhorse) and write both the
collected data and a structured report.

Goal: produce evidence about real failure modes before we commit to any
stability fixes. Don't guess — measure.

Scenarios:
  A. search(keyword, limit=1000)          -> tests multi-variant fan-out ceiling
  B. get_comments(video_id, limit=1000)   -> tests Innertube continuation
  C. get_user_posts(handle, limit=500)    -> tests flat-playlist extraction

Usage:
  python examples/baseline_1k.py

Output:
  /tmp/baseline_1k/search.jsonl
  /tmp/baseline_1k/comments.jsonl
  /tmp/baseline_1k/user_posts.jsonl
  /tmp/baseline_1k/report.md
"""
# Make the package importable when running this file directly.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import asyncio
import json
import time
import traceback
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path


OUT_DIR = Path("/tmp/baseline_1k")
OUT_DIR.mkdir(parents=True, exist_ok=True)

KEYWORD = "python tutorial"
VIDEO_ID = "kJQP7kiw5Fk"          # Despacito, millions of comments available
CHANNEL = "MrBeast"                # ~850 uploads, safe for limit=500

# Per-phase overall timeout (seconds). A single phase blowing up shouldn't
# eat the whole run — the next phase still gets its chance.
PHASE_TIMEOUT = 900


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


def dup_count(items, id_attr="source_id"):
    ids = [getattr(it, id_attr, None) for it in items]
    ids = [i for i in ids if i]
    return len(ids) - len(set(ids))


async def run_phase(label, coro, target):
    """Run one phase, capture result + structured failure info."""
    rec = {
        "label": label,
        "target": target,
        "start": datetime.now().isoformat(),
        "ok": False,
        "got": 0,
        "elapsed_s": 0.0,
        "throughput_per_s": 0.0,
        "error_type": None,
        "error_msg": None,
        "duplicates": 0,
    }
    print(f"\n>>> {label} (target={target})")
    t0 = time.time()
    try:
        items = await asyncio.wait_for(coro, timeout=PHASE_TIMEOUT)
        elapsed = time.time() - t0
        rec["ok"] = True
        rec["got"] = len(items)
        rec["elapsed_s"] = round(elapsed, 1)
        rec["throughput_per_s"] = round(len(items) / max(elapsed, 0.001), 2)
        rec["duplicates"] = dup_count(items)
        print(f"    OK: {len(items)}/{target} in {elapsed:.1f}s "
              f"({rec['throughput_per_s']}/s, dups={rec['duplicates']})")
        return rec, items
    except asyncio.TimeoutError:
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rec["error_type"] = "TimeoutError"
        rec["error_msg"] = f"phase exceeded {PHASE_TIMEOUT}s"
        print(f"    TIMEOUT after {PHASE_TIMEOUT}s")
        return rec, []
    except Exception as e:
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rec["error_type"] = type(e).__name__
        rec["error_msg"] = str(e)[:300]
        print(f"    FAIL {type(e).__name__}: {str(e)[:200]}")
        traceback.print_exc(limit=3)
        return rec, []


def write_report(phases):
    lines = [
        "# Baseline 1K Report",
        "",
        f"- Run at: {datetime.now().isoformat()}",
        f"- Crawler under test: `YtdlpYouTubeCrawler`",
        "",
        "## Results",
        "",
        "| Phase | Target | Got | Elapsed | Throughput | Dups | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in phases:
        status = "OK" if p["ok"] else f"FAIL ({p['error_type']})"
        coverage = f"{p['got']}/{p['target']}"
        pct = (p["got"] / p["target"] * 100) if p["target"] else 0
        lines.append(
            f"| {p['label']} | {p['target']} | {coverage} ({pct:.0f}%) "
            f"| {p['elapsed_s']}s | {p['throughput_per_s']}/s "
            f"| {p['duplicates']} | {status} |"
        )

    lines += ["", "## Observations (auto-derived)", ""]
    for p in phases:
        bullets = []
        if not p["ok"]:
            bullets.append(f"- failed with `{p['error_type']}`: {p['error_msg']}")
        else:
            if p["target"] and p["got"] < p["target"] * 0.8:
                shortfall_pct = (1 - p["got"] / p["target"]) * 100
                bullets.append(
                    f"- collected only {p['got']}/{p['target']} "
                    f"({shortfall_pct:.0f}% shortfall) — check if this is a hard ceiling"
                )
            if p["duplicates"] > 0:
                bullets.append(
                    f"- {p['duplicates']} duplicate source_id(s) — global dedup layer would help"
                )
            if p["throughput_per_s"] < 1.0 and p["got"] > 0:
                bullets.append(
                    f"- {p['throughput_per_s']}/s is slow for this scale — candidate for concurrency"
                )
        if bullets:
            lines.append(f"### {p['label']}")
            lines.extend(bullets)
            lines.append("")

    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {OUT_DIR / 'report.md'}")


async def main():
    from youtube_crawler.ytdlp_crawler import YtdlpYouTubeCrawler

    print(f"Baseline 1K start: {datetime.now().isoformat()}")
    print(f"Output dir: {OUT_DIR}")

    crawler = YtdlpYouTubeCrawler()

    phases = []

    # A. search
    rec, items = await run_phase(
        "A. search (yt-dlp)",
        crawler.search(KEYWORD, limit=1000),
        target=1000,
    )
    write_jsonl(OUT_DIR / "search.jsonl", items)
    phases.append(rec)

    # B. comments
    rec, items = await run_phase(
        "B. get_comments (yt-dlp→visible)",
        crawler.get_comments(VIDEO_ID, limit=1000),
        target=1000,
    )
    write_jsonl(OUT_DIR / "comments.jsonl", items)
    phases.append(rec)

    # C. user_posts
    rec, items = await run_phase(
        "C. get_user_posts (yt-dlp)",
        crawler.get_user_posts(CHANNEL, limit=500),
        target=500,
    )
    write_jsonl(OUT_DIR / "user_posts.jsonl", items)
    phases.append(rec)

    try:
        await crawler.close()
    except Exception:
        pass

    write_report(phases)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for p in phases:
        status = "OK" if p["ok"] else f"FAIL ({p['error_type']})"
        print(f"  {p['label']:40} {p['got']}/{p['target']}  {p['elapsed_s']}s  {status}")


if __name__ == "__main__":
    asyncio.run(main())
