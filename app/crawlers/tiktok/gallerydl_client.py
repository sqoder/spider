"""
gallery-dl client for TikTok content extraction.
Handles user profiles, video metadata, and media downloads.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import CrawlError, MediaDownloadError


class GalleryDLClient:
    """
    Wrapper around gallery-dl for TikTok content extraction.
    Runs gallery-dl as a subprocess.
    """

    def __init__(self, platform: str = "tiktok"):
        settings = get_settings()
        self.platform = platform
        self.download_dir = settings.media_path / platform
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Cookies file (needed for some TikTok features)
        if platform == "tiktok":
            self.cookies_file = settings.tiktok_cookies_file
        elif platform == "instagram":
            self.cookies_file = settings.instagram_cookies_file
        else:
            self.cookies_file = None

        self.proxy = settings.proxy_url

    async def extract_metadata(self, url: str) -> list[dict[str, Any]]:
        """
        Extract metadata from a URL without downloading files.

        Args:
            url: Content URL

        Returns:
            List of metadata dicts for each item found
        """
        import sys

        cmd = [
            sys.executable,
            "-m",
            "gallery_dl",
            "--dump-json",
            "--no-download",
            url,
        ]

        if self.cookies_file:
            cmd.extend(["--cookies", self.cookies_file])
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"gallery-dl extraction failed for {url}: {error_msg}")
                raise CrawlError(self.platform, "extract_metadata", error_msg)

            # gallery-dl outputs one JSON array per line
            output = stdout.decode("utf-8").strip()
            results = []
            for line in output.split("\n"):
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if isinstance(data, list) and len(data) >= 3:
                            # gallery-dl format: [category, subcategory, metadata_dict]
                            results.append(data[2] if isinstance(data[2], dict) else {"raw": data})
                        elif isinstance(data, dict):
                            results.append(data)
                    except json.JSONDecodeError:
                        continue

            return results

        except TimeoutError as e:
            raise CrawlError(self.platform, "extract_metadata", "Timed out (120s)") from e

    async def download(
        self,
        url: str,
        output_dir: str | None = None,
    ) -> list[Path]:
        """
        Download media from a URL.

        Args:
            url: Content URL
            output_dir: Optional custom output directory

        Returns:
            List of downloaded file paths
        """
        dest = Path(output_dir) if output_dir else self.download_dir

        cmd = [
            "gallery-dl",
            "--dest",
            str(dest),
            "--write-metadata",
            url,
        ]

        if self.cookies_file:
            cmd.extend(["--cookies", self.cookies_file])
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                raise MediaDownloadError(url, error_msg)

            # Parse downloaded file paths from stdout
            output = stdout.decode("utf-8").strip()
            downloaded = []
            for line in output.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    path = Path(line)
                    if path.exists():
                        downloaded.append(path)

            logger.info(f"Downloaded {len(downloaded)} files from {url}")
            return downloaded

        except TimeoutError as e:
            raise MediaDownloadError(url, "Download timed out (10 min limit)") from e

    async def get_user_content(self, username: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get content metadata from a user's profile.

        Args:
            username: Platform username
            limit: Maximum items to retrieve

        Returns:
            List of content metadata dicts
        """
        if self.platform == "tiktok":
            url = f"https://www.tiktok.com/@{username}"
        elif self.platform == "instagram":
            url = f"https://www.instagram.com/{username}/"
        else:
            raise CrawlError(self.platform, "get_user_content", "Unsupported platform")

        cmd = [
            "gallery-dl",
            "--dump-json",
            "--no-download",
            "--range",
            f"1-{limit}",
            url,
        ]

        if self.cookies_file:
            cmd.extend(["--cookies", self.cookies_file])
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            output = stdout.decode("utf-8").strip()
            results = []
            for line in output.split("\n"):
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if isinstance(data, list) and len(data) >= 3:
                            results.append(data[2] if isinstance(data[2], dict) else {"raw": data})
                        elif isinstance(data, dict):
                            results.append(data)
                    except json.JSONDecodeError:
                        continue

            return results[:limit]

        except TimeoutError as e:
            raise CrawlError(self.platform, "get_user_content", "Timed out") from e
