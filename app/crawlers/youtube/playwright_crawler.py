"""
YouTube Playwright Crawler implementation.
Mimics MediaCrawler by using direct web scraping (Playwright) to bypass API Key requirements.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Optional

from loguru import logger
from playwright.async_api import Page, async_playwright

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult


class PlaywrightYouTubeCrawler(BaseCrawler):
    """
    YouTube crawler using Playwright for direct web scraping.
    Requires NO API KEY.
    """

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self._playwright = None
        self._browser = None

    async def _init_browser(self):
        if not self._browser:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """Search YouTube using Playwright by parsing ytInitialData."""
        logger.info(f"[Playwright] Searching YouTube: {keyword}")
        await self._init_browser()
        page = await self._browser.new_page()

        results = []
        try:
            url = f"https://www.youtube.com/results?search_query={keyword}"
            await page.goto(url, wait_until="domcontentloaded")

            # YouTube stores the initial data in a global window variable `ytInitialData`
            # We can evaluate javascript to extract it directly!
            yt_data = await page.evaluate("() => { return window.ytInitialData; }")

            if not yt_data:
                logger.warning("ytInitialData not found. Retrying with delay...")
                await asyncio.sleep(2)
                yt_data = await page.evaluate("() => { return window.ytInitialData; }")

            if not yt_data:
                raise Exception("Failed to extract ytInitialData from page")

            # Parse the deeply nested JSON structure
            contents = yt_data.get("contents", {})
            two_column = contents.get("twoColumnSearchResultsRenderer", {})
            primary_contents = two_column.get("primaryContents", {})
            section_list = primary_contents.get("sectionListRenderer", {})

            for content in section_list.get("contents", []):
                item_section = content.get("itemSectionRenderer", {})
                for item in item_section.get("contents", []):
                    if "videoRenderer" in item:
                        video = item["videoRenderer"]

                        video_id = video.get("videoId")
                        title = (
                            video.get("title", {}).get("runs", [{}])[0].get("text", "")
                        )

                        # Author info
                        owner = video.get("ownerText", {}).get("runs", [{}])[0]
                        author_name = owner.get("text", "")
                        author_url = (
                            owner.get("navigationEndpoint", {})
                            .get("commandMetadata", {})
                            .get("webCommandMetadata", {})
                            .get("url", "")
                        )
                        author_username = (
                            author_url.split("/")[-1] if author_url else ""
                        )

                        # Stats
                        view_text = video.get("viewCountText", {}).get(
                            "simpleText", "0"
                        )
                        view_count = self._parse_count(view_text)

                        result = CrawlResult(
                            platform="youtube",
                            source_id=video_id,
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            title=title,
                            content_type="video",
                            author_id=author_username,
                            author_name=author_name,
                            author_username=author_username,
                            view_count=view_count,
                            raw=video,
                        )
                        results.append(result)

                        if len(results) >= limit:
                            return results

        except Exception as e:
            logger.error(f"[Playwright] Search failed: {e}")
        finally:
            await page.close()

        return results

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Mock implementation for demonstration."""
        logger.warning("Playwright get_user_posts is mocked")
        return []

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Extract video details using Playwright by parsing ytInitialData."""
        logger.info(f"[Playwright] Extracting video detail: {url}")
        await self._init_browser()
        page = await self._browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded")
            # Wait a bit for the data to be injected into window
            await asyncio.sleep(1)
            
            yt_data = await page.evaluate("() => { return window.ytInitialData; }")
            if not yt_data:
                raise Exception("Failed to extract ytInitialData for video detail")

            # Extract from the complex nested structure
            results = yt_data.get("contents", {}).get("twoColumnWatchNextResults", {})
            results_primary = results.get("results", {}).get("results", {})
            
            # This path is highly variable on YouTube, using a defensive search
            video_primary_info = {}
            video_secondary_info = {}
            
            for content in results_primary.get("contents", []):
                if "videoPrimaryInfoRenderer" in content:
                    video_primary_info = content["videoPrimaryInfoRenderer"]
                if "videoSecondaryInfoRenderer" in content:
                    video_secondary_info = content["videoSecondaryInfoRenderer"]

            video_id = yt_data.get("currentVideoEndpoint", {}).get("watchEndpoint", {}).get("videoId")
            title = video_primary_info.get("title", {}).get("runs", [{}])[0].get("text", "")
            
            # View count
            view_text = video_primary_info.get("viewCount", {}).get("videoViewCountRenderer", {}).get("viewCount", {}).get("simpleText", "0")
            view_count = self._parse_count(view_text)

            # Author / Description
            owner = video_secondary_info.get("owner", {}).get("videoOwnerRenderer", {})
            author_name = owner.get("title", {}).get("runs", [{}])[0].get("text", "")
            author_url = owner.get("navigationEndpoint", {}).get("commandMetadata", {}).get("webCommandMetadata", {}).get("url", "")
            author_username = author_url.split("/")[-1] if author_url else ""
            
            description = video_secondary_info.get("description", {}).get("runs", [])
            description_text = "".join([r.get("text", "") for r in description])

            return CrawlResult(
                platform="youtube",
                source_id=video_id or url.split("v=")[-1],
                url=url,
                title=title,
                content=description_text,
                content_type="video",
                author_name=author_name,
                author_username=author_username,
                view_count=view_count,
                raw=yt_data,
            )

        except Exception as e:
            logger.error(f"[Playwright] Detail extraction failed: {e}")
            return CrawlResult(platform=self.platform, source_id="error", url=url)
        finally:
            await page.close()

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Extract comments using Playwright by scrolling and parsing the DOM."""
        url = f"https://www.youtube.com/watch?v={post_id}"
        logger.info(f"[Playwright] Extracting comments for: {url}")
        await self._init_browser()
        page = await self._browser.new_page()

        results = []
        try:
            await page.goto(url, wait_until="domcontentloaded")
            
            # Scroll down to trigger comment loading
            await page.evaluate("window.scrollTo(0, 800)")
            await asyncio.sleep(2)
            
            # YouTube comments are loaded asynchronously. 
            # We scroll multiple times to get more comments.
            for _ in range(min(5, (limit // 20) + 1)):
                await page.keyboard.press("PageDown")
                await asyncio.sleep(1)

            # Extract comment elements
            comment_selectors = [
                "ytd-comment-thread-renderer",
                "ytd-comment-renderer"
            ]
            
            # This is a fallback: direct DOM parsing if ytInitialData isn't enough for comments
            # For a more robust solution, we'd intercept the network responses.
            elements = await page.query_selector_all("ytd-comment-thread-renderer")
            for el in elements:
                try:
                    content_el = await el.query_selector("#content-text")
                    author_el = await el.query_selector("#author-text")
                    
                    if content_el and author_el:
                        content = await content_el.inner_text()
                        author_name = (await author_el.inner_text()).strip()
                        
                        results.append(CommentResult(
                            platform="youtube",
                            source_id=f"pw_{len(results)}",
                            content=content,
                            author_name=author_name,
                            published_at=datetime.now(), # Approximate
                        ))
                except:
                    continue
                
                if len(results) >= limit:
                    break

        except Exception as e:
            logger.error(f"[Playwright] Comment extraction failed: {e}")
        finally:
            await page.close()

        return results

    def _parse_count(self, text: str) -> int:
        """Parse '1.2M views' into 1200000"""
        if not text:
            return 0
        text = text.lower().replace(" views", "").replace(" view", "").replace(",", "")
        if "k" in text:
            return int(float(text.replace("k", "")) * 1000)
        if "m" in text:
            return int(float(text.replace("m", "")) * 1000000)
        try:
            return int(float(text))
        except:
            return 0

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
