"""
Tests for Reddit crawler URL parsing.
"""

import pytest

from app.crawlers.reddit.crawler import RedditCrawler


class TestRedditURLParsing:
    """Test Reddit URL extraction."""

    def test_standard_url(self):
        subreddit, post_id = RedditCrawler._extract_post_info(
            "https://www.reddit.com/r/Python/comments/abc123/some_title/"
        )
        assert subreddit == "Python"
        assert post_id == "abc123"

    def test_old_reddit_url(self):
        subreddit, post_id = RedditCrawler._extract_post_info(
            "https://old.reddit.com/r/programming/comments/xyz789/another_post/"
        )
        assert subreddit == "programming"
        assert post_id == "xyz789"

    def test_url_without_trailing_slash(self):
        subreddit, post_id = RedditCrawler._extract_post_info(
            "https://reddit.com/r/technology/comments/def456/post_title"
        )
        assert subreddit == "technology"
        assert post_id == "def456"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            RedditCrawler._extract_post_info("https://www.google.com")

    def test_invalid_reddit_url_raises(self):
        with pytest.raises(ValueError):
            RedditCrawler._extract_post_info("https://reddit.com/r/test")
