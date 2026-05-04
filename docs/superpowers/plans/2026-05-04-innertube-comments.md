# YouTube Innertube API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Innertube API for high-speed YouTube comment fetching, replacing/augmenting the slow Playwright-based scraping.

**Architecture:** A new `InnertubeClient` will handle the low-level API requests. It first scrapes the video page to extract session metadata (API key, context), then uses the `v1/next` endpoint with continuation tokens to paginate through comments.

**Tech Stack:** `httpx` (async), `re` (regex for extraction), `json`.

---

### Task 1: Implement InnertubeClient

**Files:**
- Create: `app/crawlers/youtube/innertube_client.py`

- [ ] **Step 1: Create the file with basic structure and extraction logic**

```python
import httpx
import re
import json
from loguru import logger
from datetime import datetime
from app.crawlers.base import CommentResult

class InnertubeClient:
    def __init__(self):
        self.client = httpx.AsyncClient(headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.api_key = None
        self.context = None

    async def _get_initial_data(self, video_id: str):
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = await self.client.get(url)
        html = response.text
        
        # Extract API Key
        api_key_match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
        if not api_key_match:
            raise Exception("Could not find INNERTUBE_API_KEY")
        self.api_key = api_key_match.group(1)
        
        # Extract Context
        context_match = re.search(r'"INNERTUBE_CONTEXT":(\{.*?\})', html)
        if not context_match:
            # Fallback to a broader search if the above fails
            context_match = re.search(r'ytcfg\.set\(\{.*?"INNERTUBE_CONTEXT":(\{.*?\})', html)
            
        if context_match:
            self.context = json.loads(context_match.group(1))
        else:
            raise Exception("Could not find INNERTUBE_CONTEXT")

        # Extract initial continuation token for comments
        # This is usually in ytInitialData
        data_match = re.search(r'var ytInitialData = (\{.*?\});', html)
        if not data_match:
            raise Exception("Could not find ytInitialData")
        
        yt_data = json.loads(data_match.group(1))
        return yt_data

    async def get_comments(self, video_id: str, limit: int = 100) -> list[CommentResult]:
        try:
            yt_data = await self._get_initial_data(video_id)
            
            # Find the continuation token in ytInitialData
            # Path: contents -> twoColumnWatchNextResults -> results -> results -> contents
            # Then look for itemSectionRenderer with sectionIdentifier "comment-item-section"
            results = []
            continuation_token = self._extract_initial_continuation(yt_data)
            
            if not continuation_token:
                logger.warning(f"No comments found or comments disabled for {video_id}")
                return []

            while continuation_token and len(results) < limit:
                data = await self._fetch_next(continuation_token)
                new_comments, continuation_token = self._parse_comment_data(data)
                results.extend(new_comments)
                
                if not new_comments:
                    break
                    
            return results[:limit]
        except Exception as e:
            logger.error(f"Innertube error: {e}")
            return []

    def _extract_initial_continuation(self, yt_data):
        # Implementation to traverse ytInitialData to find the first comment continuation
        # Usually inside itemSectionRenderer with sectionIdentifier "comment-item-section"
        contents = yt_data.get("contents", {}).get("twoColumnWatchNextResults", {}).get("results", {}).get("results", {}).get("contents", [])
        for content in contents:
            if "itemSectionRenderer" in content:
                section = content["itemSectionRenderer"]
                if section.get("sectionIdentifier") == "comment-item-section":
                    # The continuation is inside the header or contents of this section
                    # More often it's in a 'continuationItemRenderer'
                    for item in section.get("contents", []):
                        if "continuationItemRenderer" in item:
                            return item["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
        return None

    async def _fetch_next(self, token: str):
        url = f"https://www.youtube.com/youtubei/v1/next?key={self.api_key}"
        payload = {
            "context": self.context,
            "continuation": token
        }
        response = await self.client.post(url, json=payload)
        return response.json()

    def _parse_comment_data(self, data):
        comments = []
        new_token = None
        
        # v1/next response structure for comments:
        # onResponseReceivedEndpoints -> reloadContinuationItemsCommand or appendContinuationItemsAction
        endpoints = data.get("onResponseReceivedEndpoints", [])
        for endpoint in endpoints:
            command = endpoint.get("reloadContinuationItemsCommand") or endpoint.get("appendContinuationItemsAction")
            if not command: continue
            
            items = command.get("continuationItems", [])
            for item in items:
                if "commentThreadRenderer" in item:
                    comment_renderer = item["commentThreadRenderer"]["comment"]["commentRenderer"]
                    
                    author_name = comment_renderer.get("authorText", {}).get("simpleText", "")
                    content = "".join([r.get("text", "") for r in comment_renderer.get("contentText", {}).get("runs", [])])
                    comment_id = comment_renderer.get("commentId")
                    
                    comments.append(CommentResult(
                        platform="youtube",
                        source_id=comment_id,
                        content=content,
                        author_name=author_name,
                        published_at=datetime.now() # Best effort
                    ))
                elif "continuationItemRenderer" in item:
                    new_token = item["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                    
        return comments, new_token

    async def close(self):
        await self.client.aclose()
```

### Task 2: Update PlaywrightYouTubeCrawler

**Files:**
- Modify: `app/crawlers/youtube/playwright_crawler.py`

- [ ] **Step 1: Import InnertubeClient and update get_comments**

```python
from app.crawlers.youtube.innertube_client import InnertubeClient

# Inside PlaywrightYouTubeCrawler class
    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        logger.info(f"[Playwright] Extracting comments for: {post_id} using Innertube")
        
        # Try Innertube first
        client = InnertubeClient()
        try:
            results = await client.get_comments(post_id, limit)
            if results:
                logger.info(f"[Innertube] Successfully fetched {len(results)} comments")
                return results
        except Exception as e:
            logger.error(f"[Innertube] Failed, falling back to Playwright: {e}")
        finally:
            await client.close()
            
        # Fallback to existing Playwright logic
        # ... (keep existing implementation)
```

### Task 3: Write Tests

**Files:**
- Create: `tests/test_innertube.py`

- [ ] **Step 1: Create test file with mocks**

```python
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
    
    with patch.object(client.client, 'get', return_value=MagicMock(text=mock_html)):
        with patch.object(client, '_fetch_next', return_value={}):
             # Verify initial data extraction logic
             yt_data = await client._get_initial_data("test_id")
             assert client.api_key == "test_key"
             assert client.context == {"client": {}}
             token = client._extract_initial_continuation(yt_data)
             assert token == "test_token"

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
                                    "commentId": "id1"
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
    
    comments, next_token = client._parse_comment_data(mock_data)
    assert len(comments) == 1
    assert comments[0].author_name == "User1"
    assert comments[0].content == "Hello world"
    assert next_token == "next_token"
```

---

### Task 4: Integration Verification

- [ ] **Step 1: Run tests**
Run: `pytest tests/test_innertube.py`

- [ ] **Step 2: Manual test if possible (requires network)**
Run a script to fetch comments for a real video.

- [ ] **Step 3: Commit changes**
Commit message: `feat: implement Innertube API for high-speed comments`
