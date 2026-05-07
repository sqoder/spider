import sys
from unittest.mock import patch

import pytest

from run import main


def test_search_args():
    test_args = [
        "run.py",
        "search",
        "--platform",
        "youtube",
        "--keyword",
        "test",
        "--limit",
        "5",
        "--download-media",
    ]
    with (
        patch.object(sys, "argv", test_args),
        patch("run.register_all_crawlers"),
        patch("run.run_search") as mock_run_search,
    ):
        main()
        mock_run_search.assert_called_once()
        args = mock_run_search.call_args[0][0]
        assert args.platform == "youtube"
        assert args.keyword == "test"
        assert args.limit == 5
        assert args.download_media is True


def test_detail_args():
    test_args = [
        "run.py",
        "detail",
        "--platform",
        "reddit",
        "--url",
        "http://test.com",
        "--comments-limit",
        "10",
    ]
    with (
        patch.object(sys, "argv", test_args),
        patch("run.register_all_crawlers"),
        patch("run.run_detail") as mock_run_detail,
    ):
        main()
        mock_run_detail.assert_called_once()
        args = mock_run_detail.call_args[0][0]
        assert args.platform == "reddit"
        assert args.url == "http://test.com"
        assert args.comments_limit == 10
        assert args.download_media is False


def test_no_args_shows_help():
    test_args = ["run.py"]
    with (
        patch.object(sys, "argv", test_args),
        patch("run.register_all_crawlers"),
    ):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1
