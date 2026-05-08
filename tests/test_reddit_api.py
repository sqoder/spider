
import pytest
import httpx
from unittest.mock import MagicMock, patch
from app.crawlers.reddit.api_client import RedditAPIClient
from app.core.exceptions import CrawlError, RateLimitExceededError

@pytest.fixture
def reddit_client():
    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.reddit_client_id = "test_id"
        mock_settings.return_value.reddit_client_secret = "test_secret"
        mock_settings.return_value.reddit_user_agent = "test_ua"
        mock_settings.return_value.max_retries = 3
        return RedditAPIClient()

@pytest.mark.asyncio
async def test_reddit_authenticate_success(reddit_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "fake_token",
        "expires_in": 3600
    }

    with patch("httpx.Client.post", return_value=mock_response):
        await reddit_client._authenticate()
        assert reddit_client._access_token == "fake_token"
        assert reddit_client.use_oauth is True

@pytest.mark.asyncio
async def test_reddit_request_get_success(reddit_client):
    reddit_client._access_token = "fake_token"
    reddit_client._token_expires_at = 9999999999.0
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test_data"}
    mock_response.headers = {}

    with patch("httpx.Client.get", return_value=mock_response):
        result = await reddit_client._request("GET", "/test_endpoint")
        assert result == {"data": "test_data"}

@pytest.mark.asyncio
async def test_reddit_request_429_raises(reddit_client):
    reddit_client._access_token = "fake_token"
    reddit_client._token_expires_at = 9999999999.0
    
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "10"}

    with patch("httpx.Client.get", return_value=mock_response):
        with pytest.raises(RateLimitExceededError):
            await reddit_client._request("GET", "/test_endpoint")

@pytest.mark.asyncio
async def test_reddit_no_api_mode():
    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.reddit_client_id = None
        mock_settings.return_value.reddit_client_secret = None
        mock_settings.return_value.reddit_user_agent = "test_ua"
        client = RedditAPIClient()
        assert client.use_oauth is False
        assert client.base_url == "https://www.reddit.com"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"kind": "Listing"}
        mock_response.headers = {}

        with patch("httpx.Client.get", return_value=mock_response) as mock_get:
            await client._request("GET", "/r/python")
            # Should append .json
            args, kwargs = mock_get.call_args
            assert args[0] == "https://www.reddit.com/r/python.json"
