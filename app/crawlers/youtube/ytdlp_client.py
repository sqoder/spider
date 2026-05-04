"""
yt-dlp client for YouTube video/audio download and metadata extraction.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import MediaDownloadError
from app.core.proxy_manager import proxy_manager


class YtdlpClient:
    """
    Wrapper around yt-dlp for media downloading and metadata extraction.
    Runs yt-dlp as a subprocess to avoid blocking the event loop.
    """

    def __init__(self):
        settings = get_settings()
        self.download_dir = settings.media_path / "youtube"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def _run_command(self, cmd: list[str], url: str, timeout: int = 300, retry_count: int = 2) -> tuple[bytes, bytes, int]:
        """Run yt-dlp command with proxy rotation and retries."""
        for attempt in range(retry_count + 1):
            current_cmd = cmd.copy()
            if proxy_manager.enabled:
                proxy_url = proxy_manager.get_proxy()
                if proxy_url:
                    current_cmd.extend(["--proxy", proxy_url])

            try:
                process = await asyncio.create_subprocess_exec(
                    *current_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=1024 * 1024 * 50,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                
                if process.returncode == 0 or stdout:
                    return stdout, stderr, process.returncode
                
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                if attempt < retry_count:
                    logger.warning(f"yt-dlp command failed (attempt {attempt+1}): {error_msg}. Retrying with different proxy...")
                    continue
            except asyncio.TimeoutError:
                if attempt < retry_count:
                    logger.warning(f"yt-dlp command timed out (attempt {attempt+1}). Retrying...")
                    continue
                raise MediaDownloadError(url, f"Timed out after {retry_count} retries")
            except Exception as e:
                logger.error(f"Unexpected error running yt-dlp: {e}")
                raise MediaDownloadError(url, str(e))
        
        return b"", b"", 1

    async def extract_info(self, url: str) -> dict[str, Any]:
        """Extract metadata from a URL without downloading."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--ignore-errors",
            "--write-comments",
            "--write-subs",
            "--write-auto-subs",
            "--write-thumbnail",
            "--write-info-json",
            "--sub-langs", "en,zh-Hans,zh-Hant",
            url,
        ]

        stdout, stderr, returncode = await self._run_command(cmd, url)

        if returncode != 0 and not stdout:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        if not stdout:
            raise MediaDownloadError(url, "yt-dlp returned empty output")

        return json.loads(stdout.decode("utf-8"))

    async def extract_multiple_info(self, url_or_query: str, limit: int = None) -> list[dict[str, Any]]:
        """Extract metadata for multiple items (search or playlist)."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--flat-playlist",
            "--no-download",
            "--ignore-errors",
            url_or_query,
        ]
        if limit:
            cmd.extend(["--playlist-end", str(limit)])
            
        stdout, stderr, _ = await self._run_command(cmd, url_or_query)

        results = []
        for line in stdout.decode("utf-8").strip().split("\n"):
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return results

    async def download_video(
        self,
        url: str,
        format_id: Optional[str] = None,
        output_template: Optional[str] = None,
        max_quality: str = "720",
    ) -> Path:
        """Download a video."""
        if output_template is None:
            output_template = str(self.download_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-o", f"{output_template}.%(ext)s" if "%(ext)s" not in output_template else output_template,
            "--no-playlist",
            "--ignore-errors",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "--write-info-json",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", "en,zh-Hans,zh-Hant",
            "--convert-subs", "srt",
            "--add-metadata",
            "--embed-subs",
            "--embed-thumbnail",
            "--embed-chapters",
        ]

        if format_id:
            cmd.extend(["-f", format_id])
        else:
            quality = max_quality or "2160"
            cmd.extend([
                "-f", f"bestvideo[height<={quality}]+bestaudio/best/best[height<={quality}]",
                "--merge-output-format", "mp4",
            ])

        cmd.append(url)

        stdout, stderr, returncode = await self._run_command(cmd, url, timeout=600)

        if returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        # Parse output to find the downloaded file
        output_lines = stdout.decode("utf-8").strip().split("\n")
        for line in output_lines:
            if "Destination:" in line or "has already been downloaded" in line:
                filepath = line.split("Destination: ")[-1].strip() if "Destination:" in line else ""
                if filepath:
                    return Path(filepath)

        return self.download_dir

    async def download_audio(
        self,
        url: str,
        output_template: Optional[str] = None,
    ) -> Path:
        """Download audio only (as MP3)."""
        if output_template is None:
            output_template = str(self.download_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-o", output_template,
            "--no-playlist",
            "--ignore-errors",
            "-x", "--audio-format", "mp3", "--audio-quality", "192K",
            url,
        ]

        stdout, stderr, returncode = await self._run_command(cmd, url)

        if returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        return self.download_dir
