from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.youtube.ytdlp_client import YtdlpClient
from app.crawlers.youtube.ytdlp_crawler import YtdlpYouTubeCrawler


@pytest.mark.asyncio
async def test_run_command_triggers_auto_update_on_extractor_error():
    client = YtdlpClient()

    # Mock subprocess.exec to fail first with "extractor" error, then succeed
    mock_process_fail = AsyncMock()
    mock_process_fail.returncode = 1
    mock_process_fail.communicate.return_value = (
        b"",
        b"ERROR: [youtube] Signature extraction failed: extractor is outdated",
    )

    mock_process_success = AsyncMock()
    mock_process_success.returncode = 0
    mock_process_success.communicate.return_value = (b'{"id": "123"}', b"")

    mock_pip_success = AsyncMock()
    mock_pip_success.returncode = 0
    mock_pip_success.communicate.return_value = (b"Successfully installed yt-dlp", b"")

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call to yt-dlp fails
        # Second call is pip install (mocked via _auto_update_ytdlp)
        # Third call to yt-dlp succeeds
        mock_exec.side_effect = [mock_process_fail, mock_pip_success, mock_process_success]

        stdout, stderr, returncode = await client._run_command(["yt-dlp", "url"], "url")

        assert returncode == 0
        assert mock_exec.call_count == 3
        # Check if second call was pip
        args, kwargs = mock_exec.call_args_list[1]
        assert "pip" in args
        assert "install" in args
        assert "--upgrade" in args
        assert "yt-dlp" in args


@pytest.mark.asyncio
async def test_run_command_continues_on_pip_failure():
    client = YtdlpClient()

    # Mock subprocess.exec to fail first with "extractor" error, then pip fails, then yt-dlp fails again
    mock_process_fail = AsyncMock()
    mock_process_fail.returncode = 1
    mock_process_fail.communicate.return_value = (
        b"",
        b"ERROR: [youtube] Signature extraction failed: extractor is outdated",
    )

    mock_pip_fail = AsyncMock()
    mock_pip_fail.returncode = 1
    mock_pip_fail.communicate.return_value = (
        b"",
        b"ERROR: Could not find a version that satisfies the requirement yt-dlp",
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # 1. yt-dlp fails (attempt 0)
        # 2. pip fails (triggered by attempt 0)
        # 3. yt-dlp fails again (attempt 1)
        # 4. pip fails again (triggered by attempt 1)
        # 5. yt-dlp fails final time (attempt 2)
        mock_exec.side_effect = [
            mock_process_fail,  # 1
            mock_pip_fail,  # 2
            mock_process_fail,  # 3
            mock_pip_fail,  # 4
            mock_process_fail,  # 5
        ]

        stdout, stderr, returncode = await client._run_command(["yt-dlp", "url"], "url")

        # Should return the last failure result after retries
        assert returncode == 1
        # 3 yt-dlp attempts + 2 pip updates (before retry 1 and retry 2)
        assert mock_exec.call_count == 5


@pytest.mark.asyncio
async def test_run_command_adds_cookie_file_when_configured(tmp_path, monkeypatch):
    cookies = tmp_path / "youtube_cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_COOKIES_FILE", str(cookies))
    from app.core.config import get_settings

    get_settings.cache_clear()
    client = YtdlpClient()
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b'{"id": "123"}', b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        stdout, _, returncode = await client._run_command(["yt-dlp", "url"], "url")

    assert returncode == 0
    assert stdout
    args, _ = mock_exec.call_args
    assert "--cookies" in args
    assert str(cookies) in args


@pytest.mark.asyncio
async def test_extract_comments_info_uses_comment_only_command():
    client = YtdlpClient()
    with patch.object(
        client,
        "_run_command",
        new_callable=AsyncMock,
        return_value=(b'{"id": "123", "comments": []}', b"", 0),
    ) as mock_run:
        info = await client.extract_comments_info("https://youtu.be/abc12345678", max_comments=7)

    assert info["id"] == "123"
    assert mock_run.await_args is not None
    cmd = mock_run.await_args.args[0]
    assert "--write-comments" in cmd
    assert "youtube:max_comments=7,7,7,7" in cmd
    assert "--write-subs" not in cmd
    assert "--write-auto-subs" not in cmd
    assert "--write-thumbnail" not in cmd
    assert "--write-info-json" not in cmd


@pytest.mark.asyncio
async def test_ytdlp_crawler_comments_uses_cached_visible_helper():
    crawler = YtdlpYouTubeCrawler()
    comments = []

    with (
        patch(
            "app.crawlers.youtube.visible_crawler.VisibleYouTubeCrawler.get_comments",
            new_callable=AsyncMock,
            return_value=comments,
        ),
        patch(
            "app.crawlers.youtube.visible_crawler.VisibleYouTubeCrawler.__init__",
            return_value=None,
        ) as mock_init,
        patch(
            "app.crawlers.youtube.visible_crawler.VisibleYouTubeCrawler.close",
            new_callable=AsyncMock,
        ) as mock_close,
        patch(
            "app.crawlers.youtube.playwright_crawler.PlaywrightYouTubeCrawler.__init__",
            side_effect=AssertionError("old Playwright helper should not be used"),
        ),
    ):
        # First call: should create and cache the visible crawler
        result1 = await crawler.get_comments("vid12345678", limit=7)
        assert result1 == comments
        mock_init.assert_called_once()

        # Second call: should reuse cached instance
        result2 = await crawler.get_comments("vid99999999", limit=3)
        assert result2 == comments
        mock_init.assert_called_once()  # still only 1 init

        # close should trigger visible crawler close
        await crawler.close()
        mock_close.assert_awaited_once()
