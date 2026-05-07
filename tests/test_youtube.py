"""
Tests for YouTube crawler URL parsing and data transformation.
"""

import pytest

from app.crawlers.youtube.crawler import YouTubeCrawler


class TestYouTubeURLParsing:
    """Test YouTube video ID extraction from various URL formats."""

    def test_standard_url(self):
        vid = YouTubeCrawler._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_short_url(self):
        vid = YouTubeCrawler._extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_embed_url(self):
        vid = YouTubeCrawler._extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        vid = YouTubeCrawler._extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_bare_id(self):
        vid = YouTubeCrawler._extract_video_id("dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_url_with_params(self):
        vid = YouTubeCrawler._extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120&list=PLxxx"
        )
        assert vid == "dQw4w9WgXcQ"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            YouTubeCrawler._extract_video_id("https://www.google.com")


class TestYouTubeDatetimeParsing:
    """Test YouTube datetime parsing."""

    def test_iso_format(self):
        dt = YouTubeCrawler._parse_datetime("2024-01-15T10:30:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_yyyymmdd_format(self):
        dt = YouTubeCrawler._parse_datetime("20240115")
        assert dt is not None
        assert dt.year == 2024

    def test_none_input(self):
        assert YouTubeCrawler._parse_datetime(None) is None

    def test_empty_string(self):
        assert YouTubeCrawler._parse_datetime("") is None

    def test_invalid_format(self):
        assert YouTubeCrawler._parse_datetime("not-a-date") is None
