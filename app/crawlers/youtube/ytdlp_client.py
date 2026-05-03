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


class YtdlpClient:
    """
    Wrapper around yt-dlp for media downloading and metadata extraction.
    Runs yt-dlp as a subprocess to avoid blocking the event loop.
    """

    def __init__(self):
        settings = get_settings()
        self.download_dir = settings.media_path / "youtube"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = settings.proxy_url

    async def extract_info(self, url: str) -> dict[str, Any]:
        """
        Extract metadata from a URL without downloading.

        Args:
            url: Video URL

        Returns:
            Dict with video metadata (title, duration, formats, etc.)
        """
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url,
        ]
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"yt-dlp info extraction failed: {error_msg}")
                raise MediaDownloadError(url, error_msg)

            return json.loads(stdout.decode("utf-8"))

        except asyncio.TimeoutError:
            raise MediaDownloadError(url, "yt-dlp metadata extraction timed out")
        except json.JSONDecodeError as e:
            raise MediaDownloadError(url, f"Failed to parse yt-dlp output: {e}")

    async def download_video(
        self,
        url: str,
        format_id: Optional[str] = None,
        output_template: Optional[str] = None,
        max_quality: str = "720",
    ) -> Path:
        """
        Download a video.

        Args:
            url: Video URL
            format_id: Specific format ID to download
            output_template: Custom output filename template
            max_quality: Maximum video height (e.g., '720', '1080')

        Returns:
            Path to the downloaded file
        """
        if output_template is None:
            output_template = str(self.download_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-o",
            output_template,
            "--no-playlist",
            "--write-thumbnail",
            "--convert-thumbnails",
            "jpg",
        ]

        if format_id:
            cmd.extend(["-f", format_id])
        else:
            # Best video up to max_quality + best audio, merged
            cmd.extend(
                [
                    "-f",
                    f"bestvideo[height<={max_quality}]+bestaudio/best[height<={max_quality}]",
                    "--merge-output-format",
                    "mp4",
                ]
            )

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        cmd.append(url)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=600  # 10 min timeout for downloads
            )

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"yt-dlp download failed: {error_msg}")
                raise MediaDownloadError(url, error_msg)

            # Parse output to find the downloaded file
            output_lines = stdout.decode("utf-8").strip().split("\n")
            logger.info(f"Video downloaded successfully: {url}")

            # Try to find the output file
            for line in output_lines:
                if "Destination:" in line or "has already been downloaded" in line:
                    filepath = (
                        line.split("Destination: ")[-1].strip()
                        if "Destination:" in line
                        else ""
                    )
                    if filepath:
                        return Path(filepath)

            # Fallback: look for the file in download dir
            return self.download_dir

        except asyncio.TimeoutError:
            raise MediaDownloadError(url, "Download timed out (10 min limit)")

    async def download_audio(
        self,
        url: str,
        output_template: Optional[str] = None,
    ) -> Path:
        """
        Download audio only (as MP3).

        Args:
            url: Video URL
            output_template: Custom output filename template

        Returns:
            Path to the downloaded audio file
        """
        if output_template is None:
            output_template = str(self.download_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-o",
            output_template,
            "--no-playlist",
            "-x",  # Extract audio
            "--audio-format",
            "mp3",
            "--audio-quality",
            "192K",
            url,
        ]

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                raise MediaDownloadError(url, error_msg)

            logger.info(f"Audio downloaded successfully: {url}")
            return self.download_dir

        except asyncio.TimeoutError:
            raise MediaDownloadError(url, "Audio download timed out")
