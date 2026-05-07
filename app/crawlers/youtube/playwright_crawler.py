"""
YouTube Playwright Crawler implementation.
Mimics MediaCrawler by using direct web scraping (Playwright) to bypass API Key requirements.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger
from playwright.async_api import Page
from scrapling import StealthyFetcher

from app.core.browser_manager import browser_manager
from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.youtube.innertube_client import InnertubeClient
from app.core.config import get_settings
from app.crawlers.youtube.ytdlp_client import YtdlpClient

class PlaywrightYouTubeCrawler(BaseCrawler):
    """
    YouTube crawler using Playwright for direct web scraping.
    Requires NO API KEY.
    """

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.ytdlp = YtdlpClient()

    async def _handle_consent(self, fetcher: StealthyFetcher):
        """Automatically click 'Accept All' on EU privacy popups."""
        try:
            # Scrapling adaptive find for consent button
            button = fetcher.find_similar("Accept all", "button")
            if button:
                button.click()
                await asyncio.sleep(1)
                logger.info("[Playwright] Handled privacy consent popup via Scrapling adaptive parser.")
                return
        except Exception:
            pass

        try:
            # Common selectors for YouTube's consent dialog
            selectors = [
                "button[aria-label='Accept all']",
                "button:has-text('Accept all')",
                "ytd-button-renderer:has-text('Accept all')",
                "form[action='https://consent.youtube.com/save'] button"
            ]
            page = fetcher.page
            for selector in selectors:
                try:
                    # Wait briefly for the element
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1) 
                        logger.info("[Playwright] Handled privacy consent popup via selector.")
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Playwright] No consent popup found or handled: {e}")

    async def _goto_with_consent(self, fetcher: StealthyFetcher, url: str):
        """Navigate to URL and handle consent popup."""
        await fetcher.page.goto(url, wait_until="domcontentloaded")
        await self._handle_consent(fetcher)

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """Search YouTube using Playwright by parsing ytInitialData."""
        await self._rate_limit()
        logger.info(f"[Playwright] Searching YouTube: {keyword}")
        fetcher = await browser_manager.new_fetcher(
            cookies_file=self.settings.youtube_cookies_file,
            locale="en-US",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = fetcher.page

        results = []
        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(keyword)}"
            await self._goto_with_consent(fetcher, url)

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
            await browser_manager.close_fetcher(fetcher)

        return results

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get videos from a YouTube channel using yt-dlp as backend."""
        await self._rate_limit()
        handle = username if username.startswith("@") else f"@{username}"
        url = f"https://www.youtube.com/{handle}/videos"
        logger.info(f"[Playwright] Getting channel videos via yt-dlp: {url}")
        try:
            items = await self.ytdlp.extract_multiple_info(url, limit=limit)
        except Exception as exc:
            logger.warning(f"[Playwright] yt-dlp channel fetch failed: {exc}")
            return []

        results = []
        for info in items[:limit]:
            if not info.get("id"):
                continue
            video_url = (
                info.get("original_url")
                or info.get("webpage_url")
                or f"https://www.youtube.com/watch?v={info['id']}"
            )
            results.append(
                CrawlResult(
                    platform="youtube",
                    source_id=info.get("id", ""),
                    url=video_url,
                    title=info.get("title"),
                    content=info.get("description"),
                    content_type="video",
                    author_name=info.get("channel"),
                    author_username=info.get("uploader_id"),
                    view_count=info.get("view_count", 0) or 0,
                    thumbnail_url=info.get("thumbnail"),
                    raw=info,
                )
            )
        return results

    async def get_post_detail(self, url: str) -> CrawlResult:
        """Extract video details using Playwright by parsing ytInitialData."""
        await self._rate_limit()
        logger.info(f"[Playwright] Extracting video detail: {url}")
        fetcher = await browser_manager.new_fetcher(
            cookies_file=self.settings.youtube_cookies_file,
            locale="en-US",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = fetcher.page

        try:
            await self._goto_with_consent(fetcher, url)
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
            
            # Robust Description Extraction
            description_text = ""
            # Path 1: Standard secondary info
            description_runs = video_secondary_info.get("description", {}).get("runs", [])
            if description_runs:
                description_text = "".join([r.get("text", "") for r in description_runs])
            
            # Path 2: Fallback to engagementPanels (new YouTube UI)
            if not description_text:
                panels = yt_data.get("engagementPanels", [])
                for panel in panels:
                    if "structuredDescriptionContentRenderer" in str(panel):
                        # Simple string search or deep extraction
                        try:
                            # Try to find all 'text' fields in the panel
                            def find_all_text(obj):
                                texts = []
                                if isinstance(obj, dict):
                                    if "text" in obj and isinstance(obj["text"], str):
                                        texts.append(obj["text"])
                                    for v in obj.values():
                                        texts.extend(find_all_text(v))
                                elif isinstance(obj, list):
                                    for i in obj:
                                        texts.extend(find_all_text(i))
                                return texts
                            description_text = "\n".join(find_all_text(panel))
                            break
                        except Exception: continue

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
            await browser_manager.close_fetcher(fetcher)

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        """Extract comments with multi-tier fallbacks: Innertube -> yt-dlp -> Playwright."""
        await self._rate_limit()
        logger.info(f"[YouTube] Multi-tier comment extraction for: {post_id}")
        # Build the video URL once so all tiers can use it
        url = f"https://www.youtube.com/watch?v={post_id}"

        # Tier 1: yt-dlp (handles replies natively, most robust)
        try:
            logger.info(f"[yt-dlp] Extracting comments for {post_id}")
            url = f"https://www.youtube.com/watch?v={post_id}"
            info = await self.ytdlp.extract_info_with_comments(url, max_comments=limit)
            ytdlp_comments = info.get("comments", [])
            # yt-dlp 成功返回的结果（包括空列表）直接使用，只有异常才走 Innertube 兜底
            results = []
            seen_ids: set[str] = set()
            for c in ytdlp_comments[:limit]:
                parent = c.get("parent", "")
                parent_id = None if parent in ("root", "none", post_id) else parent
                cid = c.get("id", "")
                if cid in seen_ids:
                    continue
                if cid:
                    seen_ids.add(cid)
                results.append(CommentResult(
                    platform="youtube",
                    source_id=cid,
                    content=c.get("text", ""),
                    author_name=c.get("author", ""),
                    author_id=c.get("author_id") or c.get("author_channel_id"),
                    like_count=c.get("like_count", 0) or 0,
                    reply_count=c.get("reply_count", 0) or 0,
                    parent_comment_id=parent_id,
                    published_at=datetime.fromtimestamp(c.get("timestamp", 0)) if c.get("timestamp") else None,
                ))
            logger.info(f"[yt-dlp] Success: extracted {len(results)} comments")
            return results
        except Exception as e:
            logger.warning(f"[yt-dlp] Failed: {e}")

        # Tier 2: Innertube API (Fast fallback)
        innertube = InnertubeClient()
        try:
            innertube_results = await innertube.get_comments(post_id, limit)
            if innertube_results:
                # Deduplicate against any results already collected
                deduped = [
                    r for r in innertube_results
                    if r.source_id not in seen_ids
                ]
                logger.info(f"[Innertube] Success: fetched {len(deduped)} unique comments")
                return deduped
        except Exception as e:
            logger.warning(f"[Innertube] Failed: {e}")
        finally:
            await innertube.close()

        # Tier 3: Playwright Scrolling (Visual Fallback)
        logger.info(f"[Playwright] Falling back to visual scrolling for {post_id}")
        fetcher = await browser_manager.new_fetcher(
            cookies_file=self.settings.youtube_cookies_file,
            locale="en-US",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = fetcher.page

        results = []
        try:
            await self._goto_with_consent(fetcher, url)
            await asyncio.sleep(2) # Wait for page load
            
            # 1. Human-like interaction: Click the page to focus
            await page.mouse.click(100, 100)
            
            # 2. Scroll to the comment section
            # Different YouTube versions have comments at different positions
            await page.evaluate("window.scrollTo(0, 1000)")
            await asyncio.sleep(2)
            
            # Use multiple selector strategies
            comment_selectors = [
                "ytd-comment-thread-renderer",
                "#comments",
                "ytd-item-section-renderer[section-identifier='comment-item-section']"
            ]
            
            found = False
            for selector in comment_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=15000)
                    found = True
                    break
                except: continue
            
            if not found:
                logger.warning(f"[Playwright] Could not find comment section via selectors. Forcing scroll.")
                for _ in range(3):
                    await page.keyboard.press("PageDown")
                    await asyncio.sleep(2)

            # 3. Aggressive scrolling to load more
            last_len = 0
            for _ in range(5):
                await page.keyboard.press("End")
                await asyncio.sleep(2)
                current_elements = await page.query_selector_all("ytd-comment-thread-renderer")
                if len(current_elements) >= limit or (len(current_elements) == last_len and last_len > 0):
                    break
                last_len = len(current_elements)

            # 4. Extract with fallback selectors
            elements = await page.query_selector_all("ytd-comment-thread-renderer")
            logger.info(f"[Playwright] Found {len(elements)} comments")
            
            for el in elements:
                try:
                    # Try different paths for content
                    content_el = await el.query_selector("#content-text") or await el.query_selector("yt-formatted-string")
                    author_el = await el.query_selector("#author-text") or await el.query_selector("#author-name")
                    
                    if content_el and author_el:
                        content = await content_el.inner_text()
                        author_name = (await author_el.inner_text()).strip()
                        
                        results.append(CommentResult(
                            platform="youtube",
                            source_id=f"pw_{len(results)}",
                            content=content,
                            author_name=author_name,
                            published_at=datetime.now(),
                        ))
                except: continue
                
                if len(results) >= limit: break

        except Exception as e:
            logger.error(f"[Playwright] Final fallback comment extraction failed: {e}")
        finally:
            await browser_manager.close_fetcher(fetcher)

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
        except (ValueError, TypeError):
            return 0

    async def close(self) -> None:
        """BrowserManager handles browser lifecycle."""
        pass
