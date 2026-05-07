"""
Proxy manager for rotating proxies across requests.
Supports a simple proxy URL or a pool of proxies.
"""

from loguru import logger

from app.core.config import get_settings


class ProxyManager:
    """Manage proxy rotation for crawlers."""

    def __init__(self):
        self._proxies: list[str] = []
        self._current_index: int = 0
        self._enabled: bool = False

    def setup(self) -> None:
        """Initialize proxy settings from config."""
        settings = get_settings()
        if settings.proxy_url:
            # Support comma-separated list of proxies for a static proxy pool
            self._proxies = [p.strip() for p in settings.proxy_url.split(",") if p.strip()]
            self._enabled = bool(self._proxies)
            if self._enabled:
                logger.info(f"Proxy pool initialized with {len(self._proxies)} proxies.")
        else:
            logger.info("No proxy configured, using direct connections")

    def add_proxy(self, proxy_url: str) -> None:
        """Add a proxy to the pool."""
        self._proxies.append(proxy_url)
        self._enabled = True
        logger.debug(f"Proxy added to pool, total: {len(self._proxies)}")

    def get_proxy(self) -> str | None:
        """Get the next proxy URL using round-robin rotation, with dynamic session support for residential proxies."""
        if not self._enabled or not self._proxies:
            return None

        proxy = self._proxies[self._current_index % len(self._proxies)]
        self._current_index += 1

        # Dynamic session generation for residential proxies (e.g., Webshare, Bright Data)
        settings = get_settings()
        if settings.proxy_rotation and "-session-" in proxy:
            import uuid
            import re
            session_id = uuid.uuid4().hex[:8]
            # Replace -session-xxxx with -session-<random_id>
            proxy = re.sub(r"-session-[^:@/]+", f"-session-{session_id}", proxy)

        return proxy

    def remove_proxy(self, proxy_url: str) -> None:
        """Remove a blocked or dead proxy from the pool."""
        # Clean session IDs if dynamic to find base proxy URL match
        import re
        base_url = re.sub(r"-session-[^:@/]+", "-session-", proxy_url)
        
        match_found = False
        for p in list(self._proxies):
            p_base = re.sub(r"-session-[^:@/]+", "-session-", p)
            if p_base == base_url or p == proxy_url:
                self._proxies.remove(p)
                match_found = True
                
        if match_found:
            logger.warning(f"Removed dead proxy. Remaining: {len(self._proxies)}")
            if len(self._proxies) == 0:
                self._enabled = False

    def get_proxy_dict(self) -> dict[str, str] | None:
        """Get proxy as a dict suitable for httpx/aiohttp."""
        proxy = self.get_proxy()
        if not proxy:
            return None
        return {
            "http://": proxy,
            "https://": proxy,
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def pool_size(self) -> int:
        return len(self._proxies)


# Global proxy manager instance
proxy_manager = ProxyManager()
