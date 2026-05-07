"""
Media file storage management.
Handles organizing, tracking, and serving downloaded media files.
"""

from pathlib import Path

from loguru import logger

from app.core.config import get_settings


class MediaStorage:
    """Manage downloaded media files organized by platform."""

    def __init__(self):
        settings = get_settings()
        self.base_path = settings.media_path
        self.max_size_mb = settings.media_max_size_mb

    def get_platform_dir(self, platform: str) -> Path:
        """Get or create the directory for a platform's media."""
        path = self.base_path / platform
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_post_media_dir(self, platform: str, source_id: str) -> Path:
        """Get or create a dedicated directory for a post's media files."""
        platform_dir = self.get_platform_dir(platform)
        post_dir = platform_dir / source_id
        post_dir.mkdir(parents=True, exist_ok=True)
        return post_dir

    def get_media_path(
        self,
        platform: str,
        source_id: str,
        extension: str = "mp4",
        use_post_dir: bool = False,
    ) -> Path:
        """
        Generate a consistent file path for a media item.

        Args:
            platform: Platform name
            source_id: Platform-specific content ID
            extension: File extension
            use_post_dir: If True, put file inside a dedicated directory for this source_id

        Returns:
            Full path where the media should be stored
        """
        if use_post_dir:
            post_dir = self.get_post_media_dir(platform, source_id)
            # Standard naming within the folder
            return post_dir / f"video.{extension.lstrip('.')}"

        platform_dir = self.get_platform_dir(platform)
        filename = f"{source_id}.{extension.lstrip('.')}"
        return platform_dir / filename

    def file_exists(self, platform: str, source_id: str, extension: str = "mp4") -> bool:
        """Check if a media file already exists."""
        path = self.get_media_path(platform, source_id, extension)
        return path.exists()

    def get_file_size_mb(self, path: Path) -> float:
        """Get file size in megabytes."""
        if path.exists():
            return path.stat().st_size / (1024 * 1024)
        return 0.0

    def get_total_size_mb(self) -> float:
        """Get total size of all stored media in megabytes."""
        total = 0
        for f in self.base_path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total / (1024 * 1024)

    def has_space(self, needed_mb: float = 100) -> bool:
        """Check if there's enough storage space."""
        current = self.get_total_size_mb()
        return (current + needed_mb) <= self.max_size_mb

    def cleanup_oldest(self, free_mb: float = 500) -> int:
        """
        Delete oldest files to free up space.

        Args:
            free_mb: Amount of space to free (in MB)

        Returns:
            Number of files deleted
        """
        files = []
        for f in self.base_path.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                files.append((f, f.stat().st_mtime, f.stat().st_size))

        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x[1])

        freed = 0.0
        deleted = 0
        for filepath, _, size in files:
            if freed >= free_mb * 1024 * 1024:
                break
            try:
                filepath.unlink()
                freed += size
                deleted += 1
            except OSError as e:
                logger.warning(f"Failed to delete {filepath}: {e}")

        logger.info(f"Cleaned up {deleted} files, freed {freed / (1024 * 1024):.1f} MB")
        return deleted

    def get_stats(self) -> dict:
        """Get storage statistics."""
        total_files = 0
        total_size = 0
        by_platform = {}

        for f in self.base_path.rglob("*"):
            if f.is_file():
                total_files += 1
                total_size += f.stat().st_size
                platform = f.parent.name
                if platform not in by_platform:
                    by_platform[platform] = {"files": 0, "size_mb": 0.0}
                by_platform[platform]["files"] += 1
                by_platform[platform]["size_mb"] += f.stat().st_size / (1024 * 1024)

        return {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_size_mb": self.max_size_mb,
            "usage_percent": (
                round((total_size / (1024 * 1024)) / self.max_size_mb * 100, 1)
                if self.max_size_mb > 0
                else 0
            ),
            "by_platform": by_platform,
        }


# Global media storage instance
media_storage = MediaStorage()
