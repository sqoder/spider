"""
Base store interface for all storage implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class BaseStore(ABC):
    """
    Interface for data storage.
    Follows the MediaCrawler pattern: store_content, store_comment, store_creator.
    """

    def __init__(self, platform: str, crawler_type: str):
        self.platform = platform
        self.crawler_type = crawler_type

    @abstractmethod
    async def store_content(self, items: List[dict]):
        """Store post/video/note content."""
        pass

    @abstractmethod
    async def store_comment(self, post_id: str, items: List[dict]):
        """Store comments for a specific post."""
        pass

    @abstractmethod
    async def store_creator(self, items: List[dict]):
        """Store author/creator information."""
        pass

    @abstractmethod
    async def close(self):
        """Cleanup resources."""
        pass
