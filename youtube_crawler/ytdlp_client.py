"""
yt-dlp client for YouTube video/audio download and metadata extraction.
"""

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from youtube_crawler.core.config import get_settings
from youtube_crawler.core.exceptions import MediaDownloadError
from youtube_crawler.core.proxy_manager import proxy_manager


class YtdlpClient:
    """
    Wrapper around yt-dlp for media downloading and metadata extraction.
    Runs yt-dlp as a subprocess to avoid blocking the event loop.
    """

    def __init__(self):
        settings = get_settings()
        self.download_dir = settings.media_path / "youtube"

    def _get_base_args(self) -> list[str]:
        """Get base yt-dlp arguments including rate-limiting bypass."""
        # Using a fixed browser User-Agent can help bypass some 429s
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        args = [
            "yt-dlp",
            "--no-playlist",
            "--ignore-errors",
            "--user-agent", user_agent,
            # Add anti-ban options
            "--sleep-requests", "1",
            "--sleep-interval", "2",
            "--max-sleep-interval", "5",
            # Sometimes legacy helps with 429
            "--extractor-args", "youtube:player_client=default,web,android",
        ]
        return args

    async def _run_command(
        self, cmd_args: list[str], url: str, timeout: int = 300, retry_count: int = 2
    ) -> tuple[bytes, bytes, int]:
        """Run yt-dlp command with proxy rotation, cookies, and retries."""
        settings = get_settings()

        # Start with base args
        cmd = self._get_base_args()
        # Add specific command args (remove 'yt-dlp' if it's the first element)
        cmd.extend(cmd_args[1:] if cmd_args[0] == "yt-dlp" else cmd_args)

        for attempt in range(retry_count + 1):
            current_cmd = cmd.copy()
            subprocess_env = os.environ.copy()

            # Inject proxy via environment so it never lands in argv / ps output.
            if proxy_manager.enabled:
                proxy_url = proxy_manager.get_proxy()
                if proxy_url:
                    subprocess_env["HTTPS_PROXY"] = proxy_url
                    subprocess_env["HTTP_PROXY"] = proxy_url

            # Add cookies
            if settings.youtube_cookies_file and os.path.exists(settings.youtube_cookies_file):
                current_cmd.extend(["--cookies", settings.youtube_cookies_file])

            # URL is usually at the end, but make sure it's passed
            if url not in current_cmd:
                current_cmd.append(url)

            process: asyncio.subprocess.Process | None = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *current_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=1024 * 1024 * 50,
                    env=subprocess_env,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

                if process.returncode is None:
                    # wait_for returned without raising but returncode unset — treat as failure.
                    raise MediaDownloadError(url, "yt-dlp exited with no returncode")

                if process.returncode == 0 or stdout:
                    return stdout, stderr, process.returncode

                error_msg = stderr.decode("utf-8", errors="replace").strip()
                if attempt < retry_count:
                    logger.warning(
                        f"yt-dlp command failed (attempt {attempt + 1}): {error_msg}. Retrying with different proxy..."
                    )

                    # If we got 429 Too Many Requests or Timeout, we should sleep before retry
                    if "429" in error_msg or "Too Many Requests" in error_msg or "timed out" in error_msg.lower() or "read timed out" in error_msg.lower():
                        logger.warning("YouTube Rate Limit (429) or Timeout detected. Sleeping for 10 seconds before retry...")
                        await asyncio.sleep(10)

                    continue
            except TimeoutError as e:
                # Kill the orphaned subprocess and drain pipes to avoid zombies / FD leaks.
                if process is not None and process.returncode is None:
                    process.kill()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except TimeoutError:
                        logger.error("yt-dlp subprocess did not exit after kill()")
                    if process.stdout is not None:
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(process.stdout.read(), timeout=2)
                    if process.stderr is not None:
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(process.stderr.read(), timeout=2)

                if attempt < retry_count:
                    logger.warning(f"yt-dlp command timed out (attempt {attempt + 1}). Retrying in 10s...")
                    await asyncio.sleep(10)
                    continue
                raise MediaDownloadError(url, f"Timed out after {retry_count} retries") from e
            except Exception as e:
                logger.error(f"Unexpected error running yt-dlp: {e}")
                raise MediaDownloadError(url, str(e)) from e

        raise MediaDownloadError(url, f"yt-dlp failed after {retry_count + 1} attempts")

    async def extract_info(self, url: str) -> dict[str, Any]:
        """Extract metadata from a URL without downloading or writing files."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
        ]

        stdout, stderr, returncode = await self._run_command(cmd, url)

        if returncode != 0 and not stdout:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        if not stdout:
            raise MediaDownloadError(url, "yt-dlp returned empty output")

        return json.loads(stdout.decode("utf-8"))

    async def extract_info_with_comments(
        self, url: str, max_comments: int = 99999
    ) -> dict[str, Any]:
        """Extract metadata AND download comments/subtitles/thumbnails from a URL.

        max_comments sets yt-dlp's internal limit per video. Use 99999 for "all".
        """
        max_val = "all" if max_comments >= 99999 else str(max_comments)
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "-P",
            str(self.download_dir),
            "--write-comments",
            "--extractor-args",
            f"youtube:max_comments={max_val},{max_val},{max_val},{max_val};player_client=default,web,android",
            "--write-subs",
            "--write-auto-subs",
            "--write-thumbnail",
            "--write-info-json",
            "--sub-langs",
            "en,zh-Hans,zh-Hant",
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
            "--write-comments",
            "--extractor-args",
            f"youtube:max_comments={max_val},{max_val},{max_val},{max_val};player_client=default,web,android",
        ]

        stdout, stderr, returncode = await self._run_command(cmd, url)

        if returncode != 0 and not stdout:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        if not stdout:
            raise MediaDownloadError(url, "yt-dlp returned empty output")

        return json.loads(stdout.decode("utf-8"))

    async def extract_multiple_info(
        self, url_or_query: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Extract metadata for multiple items (search or playlist)."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--flat-playlist",
            "--no-download",
        ]
        if limit:
            cmd.extend(["--playlist-end", str(limit)])

        stdout, stderr, returncode = await self._run_command(cmd, url_or_query)

        if returncode != 0 and not stdout:
            logger.warning(
                f"yt-dlp extract_multiple_info failed: {stderr.decode('utf-8', errors='replace').strip()}"
            )
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
        format_id: str | None = None,
        output_template: str | None = None,
        max_quality: str = "720",
    ) -> Path:
        """Download a video."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if output_template is None:
            output_template = str(self.download_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-o",
            f"{output_template}.%(ext)s" if "%(ext)s" not in output_template else output_template,
            "--write-thumbnail",
            "--convert-thumbnails",
            "jpg",
            "--write-info-json",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en,zh-Hans,zh-Hant",
            "--convert-subs",
            "srt",
            "--add-metadata",
            "--embed-subs",
            "--embed-thumbnail",
            "--embed-chapters",
        ]

        if format_id:
            cmd.extend(["-f", format_id])
        else:
            quality = max_quality or "2160"
            cmd.extend(
                [
                    "-f",
                    f"bestvideo[height<={quality}]+bestaudio/best/best[height<={quality}]",
                    "--merge-output-format",
                    "mp4",
                ]
            )

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
        output_template: str | None = None,
    ) -> Path:
        """Download audio only (as MP3)."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if output_template is None:
            output_template = str(self.download_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "-o",
            output_template,
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "192K",
        ]

        stdout, stderr, returncode = await self._run_command(cmd, url)

        if returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise MediaDownloadError(url, error_msg)

        return self.download_dir

    async def close(self) -> None:
        """No-op for interface compatibility; yt-dlp has no persistent connections."""
        pass
