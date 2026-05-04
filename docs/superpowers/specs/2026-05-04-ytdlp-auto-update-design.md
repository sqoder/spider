# yt-dlp Auto-Update Mechanism Design

## Goal
YouTube frequently changes its internal logic, which often breaks older versions of yt-dlp. We need a way for the crawler to automatically update yt-dlp when it detects specific extraction errors.

## Approach
1.  **Detection**: In `YtdlpClient._run_command`, if a command fails (return code != 0), we will check the error message in `stderr`.
2.  **Trigger**: If the error message contains keywords indicating an outdated version or extractor issue (e.g., "outdated", "signature", "extractor"), we will trigger an auto-update.
3.  **Update**: A new private method `_auto_update_ytdlp` will be added to `YtdlpClient`. It will run `pip install --upgrade yt-dlp` using `asyncio.create_subprocess_exec`.
4.  **Retry**: After a successful update, the crawler will retry the failed command.

## Architecture
- `YtdlpClient._auto_update_ytdlp()`: Asynchronous method to upgrade `yt-dlp`.
- `YtdlpClient._run_command()`: Modified to call `_auto_update_ytdlp()` upon detecting relevant errors.

## Data Flow
1. `_run_command` executes `yt-dlp`.
2. `yt-dlp` fails with an "extractor" error.
3. `_run_command` detects the error and calls `_auto_update_ytdlp`.
4. `_auto_update_ytdlp` upgrades `yt-dlp`.
5. `_run_command` retries the original command.

## Error Handling
- If `pip install` fails, log the error and continue with the next retry (without update) or raise the original error if retries are exhausted.
- Use `asyncio.subprocess.PIPE` to capture `pip` output for logging.

## Testing Strategy
- Mock `asyncio.create_subprocess_exec` to simulate `yt-dlp` failure and `pip` success/failure.
- Verify that `_auto_update_ytdlp` is called when specific error strings are present.
- Verify that the command is retried after the update.
