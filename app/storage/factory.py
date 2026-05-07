"""
Store factory to create storage implementations based on configuration.
"""

from app.core.config import get_settings
from app.storage.base_store import BaseStore
from app.storage.db_store_impl import DbStoreImplement
from app.storage.file_store_impl import FileStoreImplement


class StoreFactory:
    """Factory to create the appropriate store based on config."""

    @staticmethod
    def create_store(platform: str, crawler_type: str) -> BaseStore:
        """
        Create a store instance.

        Args:
            platform: e.g., 'youtube', 'tiktok'
            crawler_type: e.g., 'search', 'detail', 'user_posts'
        """
        settings = get_settings()
        option = settings.save_data_option.lower()

        if option in ("csv", "json", "jsonl", "excel"):
            return FileStoreImplement(platform, crawler_type, option)
        elif option in ("db", "postgres", "sqlite"):
            return DbStoreImplement(platform, crawler_type)
        else:
            # Fallback to JSONL
            return FileStoreImplement(platform, crawler_type, "jsonl")
