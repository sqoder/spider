import asyncio
import httpx
from pathlib import Path
from datetime import datetime
from loguru import logger
from scrapling import Fetcher

class MediaService:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self._run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def get_run_timestamp(self) -> str:
        return self._run_timestamp

    async def download_youtube(self, url: str, source_id: str, quality: int = 360) -> None:
        """用 yt-dlp 下载 YouTube 视频 + 缩略图。"""
        media_dir = self.output_dir / "youtube" / self._run_timestamp / "media" / source_id
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
            logger.info(f"      {f.name}  ({f.stat().st_size / 1024:.1f} KB)")

    async def download_tiktok(self, url: str, source_id: str) -> None:
        """用 yt-dlp 下载 TikTok 视频 + 缩略图。"""
        media_dir = self.output_dir / "tiktok" / self._run_timestamp / "media" / source_id
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
            logger.warning("      ⚠ 视频下载失败：yt-dlp 未生成文件")
            return
            
        for f in sorted(media_dir.iterdir()):
            logger.info(f"      {f.name}  ({f.stat().st_size / 1024:.1f} KB)")

    async def download_x(self, url: str, source_id: str) -> None:
        """用 yt-dlp 下载 X/Twitter 视频、图片。"""
        media_dir = self.output_dir / "x" / self._run_timestamp / "media" / source_id
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
            logger.warning("      ⚠ 媒体下载失败或无媒体")
            return
            
        for f in sorted(files):
            logger.info(f"      {f.name}  ({f.stat().st_size / 1024:.1f} KB)")

    async def download_instagram(self, media_list: list, source_id: str) -> None:
        """使用 httpx 下载 Instagram 帖子中的图片 and 视频（通过直链）。"""
        if not media_list:
            logger.info("      无可用媒体链接")
            return
        media_dir = self.output_dir / "instagram" / self._run_timestamp / "media" / source_id
        media_dir.mkdir(parents=True, exist_ok=True)

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
                        logger.info(f"      {filename}  ({len(resp.content) / 1024:.1f} KB)")
                        idx += 1
                    else:
                        logger.debug(f"Failed to download Instagram media {murl}: HTTP {resp.status_code}")
                except Exception as e:
                    logger.debug(f"Error downloading Instagram media {murl}: {e}")

    async def download_reddit(self, media_list: list, source_id: str, post_url: str = None) -> None:
        """使用 Scrapling Fetcher 下载 Reddit 帖子中的图片和图集媒体，如果是视频则用 yt-dlp 下载。"""
        if not media_list:
            logger.info("      无可用媒体链接")
            return
        media_dir = self.output_dir / "reddit" / self._run_timestamp / "media" / source_id
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
                    logger.info(f"      已下载视频 ({video_files[0].name})")
                else:
                    logger.warning("      ⚠ 视频下载失败：yt-dlp 未生成文件")
            except Exception as e:
                logger.debug(f"yt-dlp download failed: {e}")

        # 用 Scrapling 下载常规图片 / 图集
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
                    logger.info(f"      已下载图片: {fname}  ({len(resp.content) / 1024:.1f} KB)")
                    idx += 1
                else:
                    logger.debug(f"Failed to download Reddit media {murl}: HTTP {resp.status_code}")
            except Exception as e:
                logger.debug(f"Error downloading Reddit media {murl}: {e}")
