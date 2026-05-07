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
            self._proxies = [settings.proxy_url]
            self._enabled = True
            logger.info(f"Proxy enabled: {settings.proxy_url[:30]}...")
        else:
            logger.info("No proxy configured, using direct connections")

    def add_proxy(self, proxy_url: str) -> None:
        """Add a proxy to the pool."""
        self._proxies.append(proxy_url)
        self._enabled = True
        logger.debug(f"Proxy added to pool, total: {len(self._proxies)}")

    def get_proxy(self) -> str | None:
        """Get the next proxy URL using round-robin rotation."""
        if not self._enabled or not self._proxies:
            return None

        proxy = self._proxies[self._current_index % len(self._proxies)]
        self._current_index += 1
        return proxy

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
