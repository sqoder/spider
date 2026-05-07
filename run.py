#!/usr/bin/env python3
"""
GlobalMediaCrawler — 多平台统一入口

用法：
    python run.py

平台开关、关键词、数量等均在 config.py 中配置。
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保在项目根目录运行
os.chdir(Path(__file__).parent)

# 运行时间戳（每次运行产生独立输出目录）
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

from loguru import logger

# ── 加载用户配置 ────────────────────────────────────────────
import config as cfg  # noqa: E402

# ── 设置环境变量（必须在 app 模块导入之前）─────────────────
os.environ.setdefault("SIMPLE_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/crawler.db")
os.environ.setdefault("YOUTUBE_API_KEY", "")
os.environ["ENABLED_PLATFORMS"] = ",".join(cfg.ENABLED_PLATFORMS)
os.environ.setdefault("SAVE_DATA_OPTION", "csv")
os.environ.setdefault("SAVE_DATA_PATH", "output")
os.environ["SAVE_DATA_SUBDIR"] = f"{RUN_TIMESTAMP}/text/csv"

# ── App 导入 ────────────────────────────────────────────────
from app.crawlers.factory import CrawlerFactory, register_all_crawlers  # noqa: E402
from app.storage.factory import StoreFactory  # noqa: E402

register_all_crawlers()


# ════════════════════════════════════════════════════════════
#   工具函数
# ════════════════════════════════════════════════════════════

def _platform_cfg(platform: str) -> dict:
    """从 config.py 读取指定平台的配置字典。"""
    return getattr(cfg, platform.upper(), {})


async def _download_media_youtube(url: str, source_id: str, quality: int) -> None:
    """用 yt-dlp 下载 YouTube 视频 + 缩略图。"""
    media_dir = Path("output") / "youtube" / RUN_TIMESTAMP / "media" / source_id
    media_dir.mkdir(parents=True, exist_ok=True)

    # 缩略图 + info.json
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--write-info-json", "--skip-download", "--no-playlist",
        "-o", str(media_dir / "video"), url,
    )
    await proc.wait()

    # 视频本体
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "-f", f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
        "--merge-output-format", "mp4",
        "--no-playlist", "--ignore-errors",
        "-o", str(media_dir / "video.%(ext)s"), url,
    )
    await proc.wait()

    for f in sorted(media_dir.iterdir()):
        print(f"      {f.name}  ({f.stat().st_size / 1024:.1f} KB)")


async def _download_media_tiktok(url: str, source_id: str) -> None:
    """用 yt-dlp 下载 TikTok 视频 + 缩略图。"""
    media_dir = Path("output") / "tiktok" / RUN_TIMESTAMP / "media" / source_id
    media_dir.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-playlist", "--ignore-errors",
        "-o", str(media_dir / "video.%(ext)s"), url,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    video_files = list(media_dir.glob("video.*"))
    if not video_files:
        print("      ⚠ 视频下载失败：yt-dlp 未生成文件")
        return
        
    for f in sorted(media_dir.iterdir()):
        print(f"      {f.name}  ({f.stat().st_size / 1024:.1f} KB)")


async def _download_media_x(url: str, source_id: str) -> None:
    """用 yt-dlp 下载 X/Twitter 视频、图片。"""
    media_dir = Path("output") / "x" / RUN_TIMESTAMP / "media" / source_id
    media_dir.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-playlist", "--ignore-errors",
        "-o", str(media_dir / "media_%(autonumber)s.%(ext)s"), url,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    files = list(media_dir.iterdir())
    if not files:
        print("      ⚠ 媒体下载失败或无媒体")
        return
        
    for f in sorted(files):
        print(f"      {f.name}  ({f.stat().st_size / 1024:.1f} KB)")


async def _download_media_instagram(media_list: list, source_id: str) -> None:
    """使用 httpx 下载 Instagram 帖子中的图片和视频（通过直链）。"""
    if not media_list:
        print("      无可用媒体链接")
        return
    media_dir = Path("output") / "instagram" / RUN_TIMESTAMP / "media" / source_id
    media_dir.mkdir(parents=True, exist_ok=True)

    import httpx
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    idx = 1
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        for m in media_list:
            murl = m.get("url")
            if murl:
                murl = murl.replace("\\/", "/").replace("\\", "")
            mtype = m.get("type", "image")
            if not murl:
                continue

            ext = "mp4" if mtype == "video" else "jpg"
            filename = f"media_{idx:02d}.{ext}"
            filepath = media_dir / filename

            try:
                resp = await client.get(murl)
                if resp.status_code == 200:
                    filepath.write_bytes(resp.content)
                    print(f"      {filename}  ({len(resp.content) / 1024:.1f} KB)")
                    idx += 1
                else:
                    logger.debug(f"Failed to download Instagram media {murl}: HTTP {resp.status_code}")
            except Exception as e:
                logger.debug(f"Error downloading Instagram media {murl}: {e}")


async def _download_media_reddit(media_list: list, source_id: str, post_url: str = None) -> None:
    """使用 Scrapling Fetcher 下载 Reddit 帖子中的图片和图集媒体，如果是视频则用 yt-dlp 下载。"""
    if not media_list:
        print("      无可用媒体链接")
        return
    media_dir = Path("output") / "reddit" / RUN_TIMESTAMP / "media" / source_id
    media_dir.mkdir(parents=True, exist_ok=True)

    # 如果包含视频，直接用 yt-dlp 下载（支持音频和视频轨自动合并）
    has_video = any(m.get("type") == "video" for m in media_list)
    if has_video and post_url:
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", "mp4",
                "--no-playlist", "--ignore-errors",
                "-o", str(media_dir / "video.%(ext)s"),
                post_url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            video_files = list(media_dir.glob("video.*"))
            if video_files:
                print(f"      已下载视频 ({video_files[0].name})")
            else:
                print("      ⚠ 视频下载失败：yt-dlp 未生成文件")
        except Exception as e:
            logger.debug(f"yt-dlp download failed: {e}")

    # 用 Scrapling 下载常规图片 / 图集
    from scrapling import Fetcher
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    fetcher = Fetcher(headers=headers, timeout=30000)

    idx = 1
    for m in media_list:
        mtype = m.get("type")
        murl = m.get("url")
        if not murl or mtype not in ("image", "gallery"):
            continue

        # 提取合适的文件后缀
        ext = "jpg"
        if "png" in murl.lower():
            ext = "png"
        elif "gif" in murl.lower():
            ext = "gif"

        fname = f"media_{idx}.{ext}"
        fpath = media_dir / fname

        try:
            def _do_fetch():
                return fetcher.get(murl)

            resp = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)
            if resp.status_code == 200:
                fpath.write_bytes(resp.content)
                print(f"      已下载图片: {fname}  ({len(resp.content) / 1024:.1f} KB)")
                idx += 1
            else:
                logger.debug(f"Failed to download Reddit media {murl}: HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"Error downloading Reddit media {murl}: {e}")


def _print_sep(platform: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  平台: {platform.upper()}")
    print(f"{'═' * 60}")


# ════════════════════════════════════════════════════════════
#   单帖详情 + 评论 + 媒体（通用）
# ════════════════════════════════════════════════════════════

async def process_detail(platform: str, crawler, result, index: int, total: int) -> None:
    """获取单条内容的详情、评论和媒体。"""
    pcfg = _platform_cfg(platform)
    print(f"\n  [{index}/{total}] {result.title or result.url}")
    print(f"    URL : {result.url}")

    # 详情
    if platform in ("reddit", "tiktok", "x"):
        detail = result  # Search/User dump already fetches full detail
    else:
        try:
            detail = await crawler.get_post_detail(result.url)
        except Exception as e:
            print(f"    ⚠ 详情获取失败: {e}")
            return

    metrics = detail.to_dict().get("metrics", {})
    print(
        f"    浏览: {metrics.get('view_count') or 0:,} | "
        f"点赞: {metrics.get('like_count') or 0:,} | "
        f"评论: {metrics.get('comment_count') or 0:,}"
    )

    # 保存详情
    dstore = StoreFactory.create_store(platform, "detail")
    try:
        await dstore.store_content([detail.to_dict()])

        # 评论
        if pcfg.get("comments_enabled", False):
            try:
                post_id_to_pass = detail.source_id
                if platform == "reddit":
                    subreddit = detail.visible_data.get("subreddit", "all") if hasattr(detail, 'visible_data') else "all"
                    post_id_to_pass = f"{subreddit}:{detail.source_id}"
                elif platform == "tiktok":
                    username = detail.author_username or "tiktok"
                    post_id_to_pass = f"{username}:{detail.source_id}"
                
                comments = await crawler.get_comments(
                    post_id_to_pass, limit=pcfg.get("comments_count", 50)
                )
                if not pcfg.get("include_replies", True):
                    comments = [c for c in comments if not c.parent_comment_id]
                if comments:
                    await dstore.store_comment(
                        detail.source_id, [c.to_dict() for c in comments]
                    )
                print(f"    评论: {len(comments)} 条")
            except Exception as e:
                print(f"    ⚠ 评论获取失败: {e}")
        else:
            print("    评论: 已关闭")
    finally:
        await dstore.close()

    # 媒体下载
    if pcfg.get("media_enabled", False):
        if platform == "youtube":
            print("    媒体: 下载中…")
            try:
                await _download_media_youtube(
                    result.url, detail.source_id, pcfg.get("media_quality", 360)
                )
            except Exception as e:
                print(f"    ⚠ 媒体下载失败: {e}")
        elif platform == "reddit":
            print("    媒体: 下载中…")
            try:
                await _download_media_reddit(detail.media, detail.source_id, post_url=result.url)
            except Exception as e:
                print(f"    ⚠ 媒体下载失败: {e}")
        elif platform == "tiktok":
            print("    媒体: 下载中…")
            try:
                await _download_media_tiktok(result.url, detail.source_id)
            except Exception as e:
                print(f"    ⚠ 媒体下载失败: {e}")
        elif platform == "x":
            print("    媒体: 下载中…")
            try:
                await _download_media_x(result.url, detail.source_id)
            except Exception as e:
                print(f"    ⚠ 媒体下载失败: {e}")
        elif platform == "instagram":
            print("    媒体: 下载中…")
            try:
                await _download_media_instagram(detail.media, detail.source_id)
            except Exception as e:
                print(f"    ⚠ 媒体下载失败: {e}")
        else:
            print(f"    媒体: {platform} 暂不支持自动下载")
    else:
        print("    媒体: 已关闭")


# ════════════════════════════════════════════════════════════
#   各平台爬取主流程（通用）
# ════════════════════════════════════════════════════════════

async def run_platform(platform: str) -> None:
    """运行单个平台的完整爬取流程。"""
    pcfg = _platform_cfg(platform)
    if not pcfg:
        print(f"  ⚠ {platform}: config.py 中未找到配置，跳过")
        return

    _print_sep(platform)
    mode = pcfg.get("mode", "keyword")
    print(f"  模式: {mode} | 评论: {'开' if pcfg.get('comments_enabled') else '关'} | 媒体: {'开' if pcfg.get('media_enabled') else '关'}")

    try:
        crawler = CrawlerFactory.create(platform)
    except Exception as e:
        print(f"  ✗ 爬虫初始化失败: {e}")
        return

    results = []
    try:
        # ── keyword 模式 ──────────────────────────────────
        if mode == "keyword":
            keyword = pcfg.get("keyword", "")
            limit   = pcfg.get("search_limit", 10)
            print(f"  关键词: 「{keyword}」  限制: {limit} 条")
            results = await crawler.search(keyword, limit=limit)
            print(f"  搜索到 {len(results)} 条结果")

            store = StoreFactory.create_store(platform, "search")
            try:
                await store.store_content([r.to_dict() for r in results])
            finally:
                await store.close()

        # ── url 模式 ──────────────────────────────────────
        elif mode == "url":
            from app.crawlers.base import CrawlResult
            urls = pcfg.get("urls", [])
            if not urls:
                print("  ⚠ url 模式：config 中 urls 列表为空，跳过")
                return
            print(f"  URL 列表: {len(urls)} 个")
            results = [
                CrawlResult(platform=platform, source_id="", url=u, title=u)
                for u in urls
            ]

        # ── user 模式 ─────────────────────────────────────
        elif mode == "user":
            handle = pcfg.get("user_handle", "")
            limit  = pcfg.get("user_post_limit", 10)
            print(f"  用户: @{handle}  限制: {limit} 条")
            results = await crawler.get_user_posts(handle, limit=limit)
            print(f"  获取到 {len(results)} 条帖子")

            store = StoreFactory.create_store(platform, "user_posts")
            try:
                await store.store_content([r.to_dict() for r in results])
            finally:
                await store.close()

        else:
            print(f"  ✗ 未知模式: {mode}")
            return

        # ── 逐条处理详情 ──────────────────────────────────
        for i, r in enumerate(results, 1):
            try:
                await process_detail(platform, crawler, r, i, len(results))
            except Exception as e:
                print(f"  ⚠ [{i}] 处理失败: {e}")

    except Exception as e:
        print(f"  ✗ {platform} 爬取出错: {e}")
    finally:
        try:
            await crawler.close()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
#   输出文件树
# ════════════════════════════════════════════════════════════

def show_output_tree() -> None:
    run_root = Path("output")
    if not run_root.exists():
        return
    # 只展示本次运行产生的文件
    files = [
        f for f in sorted(run_root.rglob("*"))
        if f.is_file() and RUN_TIMESTAMP in str(f)
    ]
    if not files:
        return
    print(f"\n{'═' * 60}")
    print(f"  输出文件（本次运行: {RUN_TIMESTAMP}）")
    print(f"{'═' * 60}")
    for f in files:
        rel = f.relative_to(run_root)
        print(f"  {rel}  ({f.stat().st_size / 1024:.1f} KB)")


# ════════════════════════════════════════════════════════════
#   主入口
# ════════════════════════════════════════════════════════════

async def main() -> None:
    platforms = cfg.ENABLED_PLATFORMS
    print(f"\n{'━' * 60}")
    print(f"  GlobalMediaCrawler  —  {RUN_TIMESTAMP}")
    print(f"  启用平台: {', '.join(platforms) if platforms else '（无）'}")
    print(f"{'━' * 60}")

    if not platforms:
        print("\n⚠ config.py 中 ENABLED_PLATFORMS 为空，没有平台需要爬取。")
        return

    for platform in platforms:
        await run_platform(platform)

    show_output_tree()
    print(f"\n✅ 全部完成\n")


if __name__ == "__main__":
    asyncio.run(main())
