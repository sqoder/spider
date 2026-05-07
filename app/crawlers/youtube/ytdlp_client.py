"""
yt-dlp client for YouTube video/audio download and metadata extraction.
"""

import asyncio
import json
import os
import sys
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

    async def _run_command(self, cmd: list[str], url: str, timeout: int = 300, retry_count: int = 2) -> tuple[bytes, bytes, int]:
        """Run yt-dlp command with proxy rotation, cookies, and retries."""
        settings = get_settings()
        for attempt in range(retry_count + 1):
            current_cmd = cmd.copy()
            
            # Add proxy
            if proxy_manager.enabled:
                proxy_url = proxy_manager.get_proxy()
                if proxy_url:
                    current_cmd.extend(["--proxy", proxy_url])
            
            # Add cookies
            if settings.youtube_cookies_file and os.path.exists(settings.youtube_cookies_file):
                current_cmd.extend(["--cookies", settings.youtube_cookies_file])

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
                    # Check if error indicates outdated yt-dlp
                    if any(kw in error_msg.lower() for kw in ["outdated", "signature", "extractor"]):
                        logger.warning(f"Detected potential yt-dlp extractor error: {error_msg}. Attempting auto-update...")
                        await self._auto_update_ytdlp()
                    
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

    async def _auto_update_ytdlp(self):
        """Attempt to auto-update yt-dlp when extractor errors are detected."""
        logger.info("Attempting to auto-update yt-dlp...")
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                logger.info("yt-dlp update completed successfully.")
            else:
                logger.error(f"yt-dlp update failed with exit code {process.returncode}: {stderr.decode()}")
        except Exception as e:
            logger.error(f"Failed to update yt-dlp: {e}")

    async def extract_info(self, url: str) -> dict[str, Any]:
        """Extract metadata from a URL without downloading or writing files."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--ignore-errors",
            url,
        ]

        stdout, stderr, returncode = await self._run_command(cmd, url)

        if returncode != 0 and not stdout:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        if not stdout:
            raise MediaDownloadError(url, "yt-dlp returned empty output")

        return json.loads(stdout.decode("utf-8"))

    async def extract_info_with_comments(self, url: str, max_comments: int = 99999) -> dict[str, Any]:
        """Extract metadata AND download comments/subtitles/thumbnails from a URL.

        max_comments sets yt-dlp's internal limit per video. Use 99999 for "all".
        """
        max_val = "all" if max_comments >= 99999 else str(max_comments)
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--ignore-errors",
            "-P", str(self.download_dir),
            "--write-comments",
            "--extractor-args",
            f"youtube:max_comments={max_val},{max_val},{max_val},{max_val}",
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

    async def extract_comments_info(self, url: str, max_comments: int = 99999) -> dict[str, Any]:
        """Extract metadata and comments without writing media sidecar files."""
        max_val = "all" if max_comments >= 99999 else str(max_comments)
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--ignore-errors",
            "--write-comments",
            "--extractor-args",
            f"youtube:max_comments={max_val},{max_val},{max_val},{max_val}",
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
            
        stdout, stderr, returncode = await self._run_command(cmd, url_or_query)

        if returncode != 0 and not stdout:
            logger.warning(f"yt-dlp extract_multiple_info failed: {stderr.decode('utf-8', errors='replace').strip()}")
            return []

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
        self.download_dir.mkdir(parents=True, exist_ok=True)
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
        self.download_dir.mkdir(parents=True, exist_ok=True)
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

    async def close(self) -> None:
        """No-op for interface compatibility; yt-dlp has no persistent connections."""
        pass
