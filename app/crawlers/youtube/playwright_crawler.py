"""
Playwright-based crawler for YouTube.

Mimics MediaCrawler by using direct web scraping (Playwright) to bypass API Key requirements.
This crawler has been updated to use Scrapling's StealthyFetcher for anti-bot evasion.
"""

from typing import Any
from urllib.parse import quote_plus
from datetime import datetime, UTC
import asyncio

from playwright.async_api import Page
from loguru import logger
from scrapling import StealthyFetcher

from app.crawlers.base import BaseCrawler, CrawlResult, CommentResult
from app.core.config import get_settings
from app.core.browser_manager import browser_manager


YOUTUBE_ORIGIN = "https://www.youtube.com"


class PlaywrightYouTubeCrawler(BaseCrawler):
    """
    YouTube crawler using Playwright for direct web scraping.
    """

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.settings = get_settings()

    async def _new_fetcher(self) -> StealthyFetcher:
        fetcher = await browser_manager.new_fetcher(
            cookies_file=self.settings.youtube_cookies_file,
            headless=self.settings.playwright_headless,
        )
        return fetcher

    async def _goto_with_consent(self, fetcher: StealthyFetcher, url: str):
        page = getattr(fetcher, "page", None)
        if not page:
            await fetcher.get(url)
            page = getattr(fetcher, "page", None)
        
        if page:
            await page.goto(url, wait_until="domcontentloaded")
            await self._handle_consent(fetcher)

    async def _handle_consent(self, fetcher: StealthyFetcher):
        try:
            button = fetcher.find_similar("Accept all", "button")
            if button:
                await button.click()
                return
        except Exception:
            pass

        page = getattr(fetcher, "page", None)
        if not page:
             return
             
        selectors = [
            "button[aria-label='Accept all']",
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
            "ytd-button-renderer:has-text('Accept all')",
            "form[action*='consent.youtube.com/save'] button"
        ]
        
        for selector in selectors:
            try:
                if await page.locator(selector).count() > 0:
                    button = page.locator(selector).first
                    if await button.is_visible(timeout=1000):
                        await button.click()
                        await page.wait_for_load_state("domcontentloaded")
                        return
            except Exception:
                continue

    async def search(self, keyword: str, limit: int = 10) -> list[CrawlResult]:
        logger.info(f"[Playwright] Searching YouTube for: {keyword}")
        await self._rate_limit()

        fetcher = await self._new_fetcher()
        page = getattr(fetcher, "page", None)
        results: list[CrawlResult] = []

        try:
            url = f"{YOUTUBE_ORIGIN}/results?search_query={quote_plus(keyword)}"
            await self._goto_with_consent(fetcher, url)
            
            if not page:
                page = getattr(fetcher, "page", None)
                
            if not page:
                return []

            await page.wait_for_selector("ytd-video-renderer", timeout=10000)

            # Scroll to load more
            for _ in range(5):
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(1)
                count = await page.locator("ytd-video-renderer").count()
                if count >= limit:
                    break

            elements = page.locator("ytd-video-renderer")
            count = min(await elements.count(), limit)

            for i in range(count):
                el = elements.nth(i)
                try:
                    title_el = el.locator("#video-title")
                    title = await title_el.text_content() or ""
                    title = title.strip()
                    
                    href = await title_el.get_attribute("href") or ""
                    video_url = f"{YOUTUBE_ORIGIN}{href}" if href.startswith("/") else href
                    video_id = ""
                    if "?v=" in href:
                        video_id = href.split("?v=")[1].split("&")[0]

                    channel_el = el.locator("#channel-info .yt-simple-endpoint").first
                    channel_name = await channel_el.text_content() or ""
                    channel_name = channel_name.strip()
                    
                    channel_href = await channel_el.get_attribute("href") or ""
                    channel_url = f"{YOUTUBE_ORIGIN}{channel_href}" if channel_href.startswith("/") else channel_href
                    channel_id = channel_href.split("/")[-1] if channel_href else ""

                    views_el = el.locator("#metadata-line span").first
                    views_text = await views_el.text_content() or ""
                    
                    thumb_el = el.locator("ytd-thumbnail img").first
                    thumb_url = await thumb_el.get_attribute("src") or ""

                    result = CrawlResult(
                        platform=self.platform,
                        source_id=video_id,
                        url=video_url,
                        title=title,
                        author_id=channel_id,
                        author_name=channel_name,
                        author_url=channel_url,
                        thumbnail_url=thumb_url,
                        visible_data={
                            "views_text": views_text.strip(),
                        },
                        raw_sources={"playwright": "scraped"},
                        capture_meta={
                            "method": "youtube_playwright_search",
                            "captured_at": datetime.now(UTC).isoformat()
                        }
                    )
                    results.append(result)

                except Exception as e:
                    logger.debug(f"[Playwright] Error parsing video element {i}: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"[Playwright] Search failed: {e}")
            return results
        finally:
            await browser_manager.close_fetcher(fetcher)


    async def get_user_posts(self, username: str, limit: int = 10) -> list[CrawlResult]:
        logger.info(f"[Playwright] Getting user posts for: {username}")
        await self._rate_limit()

        fetcher = await self._new_fetcher()
        results: list[CrawlResult] = []

        try:
            handle = username if username.startswith("@") else f"@{username}"
            url = f"{YOUTUBE_ORIGIN}/{handle}/videos"
            await self._goto_with_consent(fetcher, url)
            
            page = getattr(fetcher, "page", None)
            if not page:
                return []

            await page.wait_for_selector("ytd-rich-item-renderer", timeout=10000)

            # Scroll to load more
            for _ in range(5):
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(1)
                count = await page.locator("ytd-rich-item-renderer").count()
                if count >= limit:
                    break

            elements = page.locator("ytd-rich-item-renderer")
            count = min(await elements.count(), limit)

            for i in range(count):
                el = elements.nth(i)
                try:
                    title_el = el.locator("#video-title")
                    title = await title_el.text_content() or ""
                    title = title.strip()
                    
                    href = await title_el.get_attribute("href") or ""
                    video_url = f"{YOUTUBE_ORIGIN}{href}" if href.startswith("/") else href
                    video_id = ""
                    if "?v=" in href:
                        video_id = href.split("?v=")[1].split("&")[0]

                    thumb_el = el.locator("ytd-thumbnail img").first
                    thumb_url = await thumb_el.get_attribute("src") or ""

                    result = CrawlResult(
                        platform=self.platform,
                        source_id=video_id,
                        url=video_url,
                        title=title,
                        author_username=username,
                        thumbnail_url=thumb_url,
                        raw_sources={"playwright": "scraped"},
                        capture_meta={
                            "method": "youtube_playwright_user_posts",
                            "captured_at": datetime.now(UTC).isoformat()
                        }
                    )
                    results.append(result)

                except Exception as e:
                    logger.debug(f"[Playwright] Error parsing video element {i}: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"[Playwright] Get user posts failed: {e}")
            return results
        finally:
            await browser_manager.close_fetcher(fetcher)


    async def get_post_detail(self, url: str) -> CrawlResult:
        logger.info(f"[Playwright] Getting post detail for: {url}")
        await self._rate_limit()

        fetcher = await self._new_fetcher()
        
        try:
            await self._goto_with_consent(fetcher, url)
            page = getattr(fetcher, "page", None)
            if not page:
                 raise Exception("Page not initialized")

            # Try to get initial data variable first as it's more reliable
            yt_data = await page.evaluate("() => window.ytInitialData || null")
            
            if yt_data:
                from app.crawlers.youtube.visible_crawler import VisibleYouTubeCrawler
                return VisibleYouTubeCrawler.parse_watch_initial_data(url, yt_data, None)

            # Fallback to scraping DOM
            await page.wait_for_selector("h1.ytd-watch-metadata", timeout=10000)
            
            title = await page.locator("h1.ytd-watch-metadata").text_content() or ""
            
            channel_el = page.locator("ytd-video-owner-renderer a.yt-simple-endpoint").first
            channel_name = await channel_el.text_content() or ""
            channel_href = await channel_el.get_attribute("href") or ""
            channel_id = channel_href.split("/")[-1] if channel_href else ""
            
            video_id = ""
            if "?v=" in url:
                 video_id = url.split("?v=")[1].split("&")[0]

            return CrawlResult(
                platform=self.platform,
                source_id=video_id,
                url=url,
                title=title.strip(),
                author_id=channel_id,
                author_name=channel_name.strip(),
                raw_sources={"playwright": "dom_scraped"},
                capture_meta={
                    "method": "youtube_playwright_detail",
                    "captured_at": datetime.now(UTC).isoformat()
                }
            )

        except Exception as e:
            logger.error(f"[Playwright] Detail extraction failed: {e}")
            return CrawlResult(
                platform=self.platform,
                source_id="",
                url=url,
                raw_sources={},
                capture_meta={
                    "method": "youtube_playwright_detail_failed",
                    "error": str(e),
                    "captured_at": datetime.now(UTC).isoformat()
                }
            )
        finally:
            await browser_manager.close_fetcher(fetcher)


    async def get_comments(self, post_id: str, limit: int = 10) -> list[CommentResult]:
        logger.info(f"[Playwright] Fetching comments for: {post_id}")
        await self._rate_limit()
        
        # We delegate to the visible crawler's dom parsing logic
        from app.crawlers.youtube.visible_crawler import VisibleYouTubeCrawler
        crawler = VisibleYouTubeCrawler()
        return await crawler._get_comments_from_dom(post_id, limit)

    async def close(self) -> None:
        pass
