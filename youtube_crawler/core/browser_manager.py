# app/core/browser_manager.py
import asyncio
import os
from typing import Any, Optional

from loguru import logger
from scrapling import StealthyFetcher

from youtube_crawler.core.config import get_settings


class BrowserManager:
    """
    Manages browser instances using Scrapling's StealthyFetcher.
    Provides advanced anti-bot bypass and unified interface for UI-based crawlers.
    """

    _instance: Optional["BrowserManager"] = None
    _fetchers: list[StealthyFetcher]
    _cookie_cache: dict[str, tuple[float, list[dict]]]
    _semaphore: asyncio.Semaphore | None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._fetchers = []
            cls._instance._cookie_cache = {}
            cls._instance._semaphore = None
        return cls._instance

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            settings = get_settings()
            limit = max(1, settings.playwright_browser_count)
            self._semaphore = asyncio.Semaphore(limit)
        return self._semaphore

    def _parse_cookies_file(self, filepath: str) -> list[dict]:
        """Parse Netscape format cookies file into Scrapling/Playwright format."""
        current_mtime = os.path.getmtime(filepath) if os.path.exists(filepath) else 0
        if current_mtime:
            cached_mtime, cached = self._cookie_cache.get(filepath, (0, []))
            if cached_mtime == current_mtime:
                return cached

        cookies = []
        if not os.path.exists(filepath):
            return cookies

        try:
            with open(filepath) as f:
                for line in f:
                    if not line.strip() or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 7:
                        continue

                    cookies.append(
                        {
                            "name": parts[5].strip(),
                            "value": parts[6].strip(),
                            "domain": parts[0].strip(),
                            "path": parts[2].strip(),
                            "expires": int(parts[4].strip()) if parts[4].strip().isdigit() else -1,
                            "secure": parts[3].strip().upper() == "TRUE",
                        }
                    )
            self._cookie_cache[filepath] = (current_mtime, cookies)
        except Exception as e:
            logger.error(f"Failed to parse cookies file: {e}")
        return cookies

    async def new_fetcher(self, cookies_file: str | None = None, **kwargs) -> Any:
        """
        Creates a new persistent session using Scrapling's AsyncStealthySession.
        """
        semaphore = self._get_semaphore()
        await semaphore.acquire()

        try:
            cookies = []
            if cookies_file:
                cookies = self._parse_cookies_file(cookies_file)

            from youtube_crawler.core.proxy_manager import proxy_manager
            proxy = kwargs.get("proxy") or proxy_manager.get_proxy()

            from scrapling.engines._browsers._stealth import AsyncStealthySession
            
            # Scrapling session configuration
            session_kwargs = {
                "headless": kwargs.get("headless", True),
                "proxy": proxy,
                "cookies": cookies,
                "timeout": kwargs.get("timeout", 30000),
            }
            
            # Add additional scrapling config
            for k in ["useragent", "locale", "timezone_id", "block_ads", "solve_cloudflare"]:
                if k in kwargs:
                    session_kwargs[k] = kwargs[k]

            session = AsyncStealthySession(**session_kwargs)
            await session.start()
            
            # Create a persistent page for this session
            # We use the session's internal _get_page logic but managed by us
            page_info = await session._get_page(
                timeout=session_kwargs["timeout"],
                extra_headers=None,
                disable_resources=kwargs.get("disable_resources", False),
            )
            
            # Attach the page and session to a wrapper object
            fetcher = session
            fetcher.page = page_info.page  # type: ignore[attr-defined]
            fetcher._page_info = page_info  # type: ignore[attr-defined]
            fetcher._action_count = 0  # type: ignore[attr-defined]
            fetcher._max_actions = kwargs.get("max_actions", 500)  # type: ignore[attr-defined]

            if cookies:
                logger.info(f"Persistent StealthyFetcher created with {len(cookies)} cookies.")

            self._fetchers.append(fetcher)
            return fetcher
        except Exception:
            semaphore.release()
            raise

    async def close_fetcher(self, fetcher: Any) -> None:
        """Close a persistent session."""
        try:
            if hasattr(fetcher, "page"):
                await fetcher.page.close()
            if hasattr(fetcher, "close"):
                await fetcher.close()
        except Exception as e:
            logger.warning(f"Failed to close fetcher: {e}")
        finally:
            if fetcher in self._fetchers:
                self._fetchers.remove(fetcher)
            self._get_semaphore().release()

    async def record_action(self, fetcher: StealthyFetcher) -> StealthyFetcher:
        """
        Record an action (like a page load, scroll, etc.) on the fetcher.
        If the fetcher's action count exceeds its limit, automatically recycles it to prevent memory leaks.
        """
        if not hasattr(fetcher, "_action_count"):
            fetcher._action_count = 0  # type: ignore[attr-defined]
            fetcher._max_actions = 500  # type: ignore[attr-defined]

        fetcher._action_count += 1  # type: ignore[attr-defined]
        if fetcher._action_count >= fetcher._max_actions:  # type: ignore[attr-defined]
            logger.info(f"StealthyFetcher reached action limit ({fetcher._max_actions}). Recycling context to prevent memory leaks...")  # type: ignore[attr-defined]
            cookies_file = getattr(fetcher, "_cookies_file", None)
            await self.close_fetcher(fetcher)
            return await self.new_fetcher(cookies_file=cookies_file, max_actions=fetcher._max_actions)  # type: ignore[attr-defined]
        return fetcher

    async def close_all(self) -> None:
        """Close all tracked fetchers."""
        for fetcher in list(self._fetchers):
            await self.close_fetcher(fetcher)
        self._fetchers.clear()

    async def close(self):
        """Alias for close_all to maintain compatibility."""
        await self.close_all()

    async def close_context(self, target: Any) -> None:
        """Compatibility alias for closing a context or fetcher."""
        if isinstance(target, StealthyFetcher):
            await self.close_fetcher(target)
        elif hasattr(target, "context"):
            # It's likely a Playwright Page
            context = target.context
            try:
                await target.close()
                await context.close()
            except Exception as e:
                logger.warning(f"Failed to close playwright page/context: {e}")
        else:
            logger.warning(f"Unknown target type for close_context: {type(target)}")


# Compatibility alias for existing code expecting new_page
async def new_page_deprecated(cookies_file: str | None = None, **kwargs):
    logger.warning("new_page is deprecated, use new_fetcher instead.")
    return await browser_manager.new_fetcher(cookies_file, **kwargs)


browser_manager = BrowserManager()
browser_manager.new_page = new_page_deprecated  # type: ignore[attr-defined]
