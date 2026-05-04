# yt-dlp Auto-Update Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an auto-update mechanism for `yt-dlp` in `YtdlpClient` to handle extractor errors caused by outdated versions.

**Architecture:** Add `_auto_update_ytdlp` method and integrate it into `_run_command` error handling loop.

**Tech Stack:** Python, asyncio, yt-dlp, pytest.

---

### Task 1: Write failing test for auto-update trigger

**Files:**
- Create: `tests/test_ytdlp_update.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.youtube.ytdlp_client import YtdlpClient

@pytest.mark.asyncio
async def test_run_command_triggers_auto_update_on_extractor_error():
    client = YtdlpClient()
    
    # Mock subprocess.exec to fail first with "extractor" error, then succeed
    mock_process_fail = AsyncMock()
    mock_process_fail.returncode = 1
    mock_process_fail.communicate.return_value = (b"", b"ERROR: [youtube] Signature extraction failed: extractor is outdated")
    
    mock_process_success = AsyncMock()
    mock_process_success.returncode = 0
    mock_process_success.communicate.return_value = (b"{\"id\": \"123\"}", b"")
    
    mock_pip_success = AsyncMock()
    mock_pip_success.returncode = 0
    mock_pip_success.communicate.return_value = (b"Successfully installed yt-dlp", b"")

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call to yt-dlp fails
        # Second call is pip install (mocked via _auto_update_ytdlp)
        # Third call to yt-dlp succeeds
        mock_exec.side_effect = [mock_process_fail, mock_pip_success, mock_process_success]
        
        # We need to ensure _auto_update_ytdlp is called. 
        # Since it's a private method, we can either spy on it or check the mock_exec calls.
        
        stdout, stderr, returncode = await client._run_command(["yt-dlp", "url"], "url")
        
        assert returncode == 0
        assert mock_exec.call_count == 3
        # Check if second call was pip
        args, kwargs = mock_exec.call_args_list[1]
        assert "pip" in args
        assert "install" in args
        assert "--upgrade" in args
        assert "yt-dlp" in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ytdlp_update.py -v`
Expected: FAIL because `_run_command` doesn't handle "extractor" error yet.

### Task 2: Implement `_auto_update_ytdlp`

**Files:**
- Modify: `app/crawlers/youtube/ytdlp_client.py`

- [ ] **Step 1: Add `_auto_update_ytdlp` method**

```python
    async def _auto_update_ytdlp(self):
        logger.info("Attempting to auto-update yt-dlp...")
        try:
            process = await asyncio.create_subprocess_exec(
                "pip", "install", "--upgrade", "yt-dlp",
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_ytdlp_update.py -v`
Expected: Still FAIL because it's not integrated into `_run_command`.

### Task 3: Integrate auto-update into `_run_command`

**Files:**
- Modify: `app/crawlers/youtube/ytdlp_client.py`

- [ ] **Step 1: Update `_run_command` to detect extractor errors and trigger update**

```python
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                if attempt < retry_count:
                    # Check if error indicates outdated yt-dlp
                    if any(kw in error_msg.lower() for kw in ["outdated", "signature", "extractor"]):
                        logger.warning(f"Detected potential yt-dlp extractor error: {error_msg}. Attempting auto-update...")
                        await self._auto_update_ytdlp()
                    
                    logger.warning(f"yt-dlp command failed (attempt {attempt+1}): {error_msg}. Retrying...")
                    continue
```

- [ ] **Step 2: Run tests to verify it passes**

Run: `pytest tests/test_ytdlp_update.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add app/crawlers/youtube/ytdlp_client.py tests/test_ytdlp_update.py
git commit -m "feat: add yt-dlp auto-update mechanism"
```

### Task 4: Additional tests for edge cases

**Files:**
- Modify: `tests/test_ytdlp_update.py`

- [ ] **Step 1: Test when pip update fails**

Add a test case where `pip install` fails and verify that `_run_command` still retries or fails gracefully.

- [ ] **Step 2: Run all tests**

Run: `pytest tests/test_ytdlp_update.py -v`
Expected: PASS
