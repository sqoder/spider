"""
Custom exception hierarchy for the crawler system.
All crawler-related errors inherit from CrawlerBaseError.
"""


class CrawlerBaseError(Exception):
    """Base exception for all crawler errors."""

    def __init__(self, message: str = "", platform: str = "", **kwargs):
        self.platform = platform
        self.details = kwargs
        super().__init__(message)


class PlatformNotSupportedError(CrawlerBaseError):
    """Raised when an unsupported platform is requested."""

    def __init__(self, platform: str):
        super().__init__(
            message=f"Platform '{platform}' is not supported",
            platform=platform,
        )


class RateLimitExceededError(CrawlerBaseError):
    """Raised when rate limit is exceeded for a platform."""

    def __init__(self, platform: str, retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__(
            message=f"Rate limit exceeded for '{platform}', retry after {retry_after}s",
            platform=platform,
        )


class APIKeyMissingError(CrawlerBaseError):
    """Raised when a required API key is not configured."""

    def __init__(self, platform: str, key_name: str = ""):
        self.key_name = key_name
        super().__init__(
            message=f"API key for '{platform}' is not configured: {key_name}",
            platform=platform,
        )


class QuotaExhaustedError(CrawlerBaseError):
    """Raised when API quota is exhausted (e.g., YouTube daily quota)."""

    def __init__(self, platform: str, quota_used: int = 0, quota_limit: int = 0):
        self.quota_used = quota_used
        self.quota_limit = quota_limit
        super().__init__(
            message=f"API quota exhausted for '{platform}': {quota_used}/{quota_limit}",
            platform=platform,
        )


class CrawlError(CrawlerBaseError):
    """Generic crawl operation error."""

    def __init__(self, platform: str, operation: str, reason: str = ""):
        self.operation = operation
        self.reason = reason
        super().__init__(
            message=f"Crawl error on '{platform}' during '{operation}': {reason}",
            platform=platform,
        )


class MediaDownloadError(CrawlerBaseError):
    """Raised when media download fails."""

    def __init__(self, url: str, reason: str = ""):
        self.url = url
        self.reason = reason
        super().__init__(
            message=f"Failed to download media from '{url}': {reason}",
        )


class AuthenticationError(CrawlerBaseError):
    """Raised when authentication fails for a platform."""

    def __init__(self, platform: str, reason: str = ""):
        self.reason = reason
        super().__init__(
            message=f"Authentication failed for '{platform}': {reason}",
            platform=platform,
        )


class ContentNotFoundError(CrawlerBaseError):
    """Raised when requested content is not found."""

    def __init__(self, platform: str, identifier: str = ""):
        self.identifier = identifier
        super().__init__(
            message=f"Content not found on '{platform}': {identifier}",
            platform=platform,
        )
