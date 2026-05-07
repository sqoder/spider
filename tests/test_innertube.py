import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.crawlers.youtube.innertube_client import InnertubeClient

@pytest.mark.asyncio
async def test_innertube_extraction():
    client = InnertubeClient()
    
    # Mock initial page load
    mock_html = """
    <html>
    <script>
    var ytInitialData = {"contents": {"twoColumnWatchNextResults": {"results": {"results": {"contents": [
        {"itemSectionRenderer": {"sectionIdentifier": "comment-item-section", "contents": [
            {"continuationItemRenderer": {"continuationEndpoint": {"continuationCommand": {"token": "test_token"}}}}
        ]}}
    ]}}}}}};
    ytcfg.set({"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {"client": {}}});
    </script>
    </html>
    """
    
    with patch.object(client.fetcher, 'get', return_value=MagicMock(text=mock_html)):
        # Verify initial data extraction logic
        yt_data = await client._get_initial_data("test_id")
        assert client.api_key == "test_key"
        assert client.context == {"client": {}}
        token = client._extract_initial_continuation(yt_data)
        assert token == "test_token"
    await client.close()

def test_extract_json_from_ytcfg_context():
    client = InnertubeClient()
    html = 'ytcfg.set({"INNERTUBE_API_KEY":"test_key","INNERTUBE_CONTEXT":{"client":{"clientName":"WEB"}}});'
    context = client._extract_json(html, r'["\']INNERTUBE_CONTEXT["\']\s*:\s*\{')
    assert context == {"client": {"clientName": "WEB"}}

@pytest.mark.asyncio
async def test_parse_comment_data():
    client = InnertubeClient()
    mock_data = {
        "onResponseReceivedEndpoints": [{
            "appendContinuationItemsAction": {
                "continuationItems": [
                    {
                        "commentThreadRenderer": {
                            "comment": {
                                "commentRenderer": {
                                    "authorText": {"simpleText": "User1"},
                                    "contentText": {"runs": [{"text": "Hello world"}]},
                                    "commentId": "id1",
                                    "publishedTimeText": {"runs": [{"text": "1 day ago"}]},
                                    "voteCount": {"simpleText": "12"},
                                    "authorEndpoint": {
                                        "browseEndpoint": {
                                            "browseId": "UC123",
                                            "canonicalBaseUrl": "/@user1"
                                        }
                                    },
                                    "authorThumbnail": {
                                        "thumbnails": [{"url": "https://yt3/user1.jpg"}]
                                    },
                                    "pinnedCommentBadge": {
                                        "pinnedCommentBadgeRenderer": {
                                            "label": {"simpleText": "Pinned by OpenAI"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    {
                        "continuationItemRenderer": {
                            "continuationEndpoint": {
                                "continuationCommand": {
                                    "token": "next_token"
                                }
                            }
                        }
                    }
                ]
            }
        }]
    }
    
    comments, next_token, reply_tokens = client._parse_comment_data(mock_data)
    assert len(comments) == 1
    assert comments[0].author_name == "User1"
    assert comments[0].content == "Hello world"
    assert comments[0].like_count == 12
    assert comments[0].visible_data["comment_id"] == "id1"
    assert comments[0].visible_data["author_handle"] == "@user1"
    assert comments[0].visible_data["author_avatar"] == "https://yt3/user1.jpg"
    assert comments[0].visible_data["published_text"] == "1 day ago"
    assert comments[0].visible_data["is_pinned"] is True
    assert comments[0].raw_sources["innertube"]["commentId"] == "id1"
    assert comments[0].capture_meta["method"] == "innertube_comments"
    assert next_token == "next_token"
    await client.close()
