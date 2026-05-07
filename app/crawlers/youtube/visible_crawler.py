"""
Visible-first YouTube crawler.

This crawler treats the Playwright-rendered page as the primary source of truth
for fields users can see, while preserving ytInitialData, Innertube, DOM, and
yt-dlp payloads for fallback and auditing.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs

from loguru import logger
from playwright.async_api import Page

from app.core.browser_manager import browser_manager
from app.core.config import get_settings
from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.youtube.innertube_client import InnertubeClient
from app.crawlers.youtube.ytdlp_client import YtdlpClient


YOUTUBE_ORIGIN = "https://www.youtube.com"
YOUTUBE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class VisibleYouTubeCrawler(BaseCrawler):
    """YouTube crawler focused on visible page data."""

    platform = "youtube"

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.ytdlp = YtdlpClient()

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        logger.info(f"[YouTube visible] Searching: {keyword}")
        await self._rate_limit()
        page = await self._new_page()
        results: list[CrawlResult] = []
        page_url = f"{YOUTUBE_ORIGIN}/results?search_query={quote_plus(keyword)}"

        try:
            await self._goto_with_consent(page, page_url)
            await self._scroll_for_items(page, limit)
            yt_data = await self._yt_initial_data(page)
            if not yt_data:
                logger.warning("[YouTube visible] ytInitialData missing on search page")
                return []

            rank = 1
            for item in self._iter_video_renderers(yt_data):
                result = self.parse_search_video_renderer(
                    item["renderer"],
                    rank=rank,
                    page_url=page_url,
                    full_yt_initial_data=yt_data,
                    renderer_type=item["type"],
                )
                if result.source_id:
                    results.append(result)
                    rank += 1
                if len(results) >= limit:
                    break

            if results:
                return results[:limit]

            logger.warning("[YouTube visible] No video renderers found in search data")
            return []
        except Exception as exc:
            logger.exception(f"[YouTube visible] Search failed: {exc}")
            return results[:limit]
        finally:
            await browser_manager.close_context(page)

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        await self._rate_limit()
        handle = username if username.startswith("@") else f"@{username}"
        url = f"{YOUTUBE_ORIGIN}/{handle}/videos"
        logger.info(f"[YouTube visible] Getting channel videos: {url}")
        try:
            items = await self.ytdlp.extract_multiple_info(url, limit=limit)
        except Exception as exc:
            logger.warning(f"[YouTube visible] yt-dlp channel fallback failed: {exc}")
            return []

        return [
            self._parse_ytdlp_info(item, method="youtube_visible_channel_fallback")
            for item in items[:limit]
            if item.get("id")
        ]

    async def get_post_detail(self, url: str) -> CrawlResult:
        logger.info(f"[YouTube visible] Extracting detail: {url}")
        await self._rate_limit()
        page = await self._new_page()
        ytdlp_info: dict[str, Any] | None = None

        try:
            await self._goto_with_consent(page, url)
            await self._expand_description(page)
            yt_data = await self._yt_initial_data(page)
            dom_snapshot = await self._dom_snapshot(page)

            try:
                ytdlp_info = await self.ytdlp.extract_info(url)
            except Exception as exc:
                logger.warning(f"[YouTube visible] yt-dlp detail fallback failed: {exc}")

            result = self.parse_watch_initial_data(url, yt_data or {}, ytdlp_info)
            result.raw_sources["dom_snapshot"] = dom_snapshot
            result.capture_meta.update(self._capture_meta("youtube_visible_detail", url))
            return result
        except Exception as exc:
            logger.exception(f"[YouTube visible] Detail extraction failed: {exc}")
            if ytdlp_info:
                result = self._parse_ytdlp_info(
                    ytdlp_info,
                    method="youtube_visible_detail_ytdlp_fallback",
                )
                result.capture_meta["fallback_reason"] = str(exc)
                return result
            video_id = self._extract_video_id(url) or url
            return CrawlResult(
                platform=self.platform,
                source_id=video_id,
                url=url,
                raw_sources={},
                capture_meta={
                    **self._capture_meta("youtube_visible_detail_failed", url),
                    "error": str(exc),
                },
            )
        finally:
            await browser_manager.close_context(page)

    async def get_comments(self, post_id: str, limit: int = 50) -> list[CommentResult]:
        logger.info(f"[YouTube visible] Fetching comments for: {post_id}")
        await self._rate_limit()
        video_id = self._extract_video_id(post_id) or post_id

        innertube = InnertubeClient()
        try:
            comments = await innertube.get_comments(video_id, limit=limit)
            if comments:
                for comment in comments:
                    comment.capture_meta.update(
                        self._capture_meta(
                            comment.capture_meta.get("method") or "innertube_comments",
                            f"{YOUTUBE_ORIGIN}/watch?v={video_id}",
                            limit=limit,
                        )
                    )
                return comments[:limit]
        except Exception as exc:
            logger.warning(f"[YouTube visible] Innertube comments failed: {exc}")
        finally:
            await innertube.close()

        try:
            info = await self.ytdlp.extract_comments_info(
                f"{YOUTUBE_ORIGIN}/watch?v={video_id}",
                max_comments=limit,
            )
            raw_comments = info.get("comments") or []
            if raw_comments:
                return [
                    self._parse_ytdlp_comment(
                        raw,
                        position=idx + 1,
                        video_id=video_id,
                        limit=limit,
                    )
                    for idx, raw in enumerate(raw_comments[:limit])
                ]
        except Exception as exc:
            logger.warning(f"[YouTube visible] yt-dlp comments failed: {exc}")

        return await self._get_comments_from_dom(video_id, limit)

    @classmethod
    def parse_search_video_renderer(
        cls,
        renderer: dict[str, Any],
        rank: int,
        page_url: str,
        full_yt_initial_data: dict[str, Any] | None = None,
        renderer_type: str = "videoRenderer",
    ) -> CrawlResult:
        video_id = renderer.get("videoId") or renderer.get("videoIdText")
        endpoint = renderer.get("navigationEndpoint") or {}
        endpoint_url = cls._endpoint_url(endpoint)
        if not video_id and endpoint_url:
            video_id = cls._extract_video_id(endpoint_url)

        card_type = "short" if renderer_type == "reelItemRenderer" else "video"
        url = cls._video_url(video_id, endpoint_url, is_short=card_type == "short")
        title = cls._text(renderer.get("title")) or cls._text(renderer.get("headline"))
        thumbnail_urls = cls._thumbnail_urls(renderer.get("thumbnail"))
        duration_text = cls._text(renderer.get("lengthText")) or cls._text(
            renderer.get("thumbnailOverlays")
        )
        owner_run = cls._first_run(
            renderer.get("ownerText")
            or renderer.get("longBylineText")
            or renderer.get("shortBylineText")
        )
        channel_name = owner_run.get("text") or cls._text(renderer.get("ownerText"))
        channel_url = cls._absolute_youtube_url(
            cls._endpoint_url(owner_run.get("navigationEndpoint", {}))
        )
        channel_handle = cls._channel_handle(channel_url)
        channel_avatar = cls._last_thumbnail_url(
            renderer.get("channelThumbnailSupportedRenderers", {})
            .get("channelThumbnailWithLinkRenderer", {})
            .get("thumbnail")
        )
        owner_badges = cls._badges(renderer.get("ownerBadges"))
        card_badges = cls._badges(renderer.get("badges"))
        badges = cls._dedupe(owner_badges + card_badges)
        view_count_text = cls._text(renderer.get("viewCountText"))
        published_text = cls._text(renderer.get("publishedTimeText"))
        description_snippet = cls._description_snippet(renderer)
        is_live = bool(
            renderer.get("badges")
            and any("live" in badge.lower() for badge in card_badges)
        ) or "watching" in view_count_text.lower()
        is_upcoming = bool(renderer.get("upcomingEventData"))
        is_short = card_type == "short" or "/shorts/" in (url or "")

        visible_data = {
            "card_type": card_type,
            "rank": rank,
            "video_id": video_id,
            "url": url,
            "title": title,
            "thumbnail_urls": thumbnail_urls,
            "duration_text": duration_text,
            "duration_seconds": cls._parse_duration(duration_text),
            "channel_name": channel_name,
            "channel_handle": channel_handle,
            "channel_url": channel_url,
            "channel_avatar": channel_avatar,
            "channel_verified": cls._is_verified(owner_badges),
            "view_count_text": view_count_text,
            "view_count": cls._parse_count(view_count_text),
            "published_text": published_text,
            "description_snippet": description_snippet,
            "badges": badges,
            "is_live": is_live,
            "is_upcoming": is_upcoming,
            "is_short": is_short,
        }

        return CrawlResult(
            platform="youtube",
            source_id=video_id or "",
            url=url,
            title=title,
            content=description_snippet,
            content_type="short" if is_short else "video",
            author_id=channel_handle,
            author_name=channel_name,
            author_username=channel_handle,
            author_url=channel_url,
            author_avatar=channel_avatar,
            view_count=visible_data["view_count"],
            thumbnail_url=thumbnail_urls[-1] if thumbnail_urls else None,
            media=[
                {
                    "type": "thumbnail",
                    "urls": thumbnail_urls,
                    "duration_text": duration_text,
                    "duration_seconds": visible_data["duration_seconds"],
                }
            ],
            raw=renderer,
            visible_data=visible_data,
            raw_sources={
                "yt_initial_data": full_yt_initial_data,
                "renderer": renderer,
            },
            capture_meta={
                **cls._capture_meta("youtube_visible_search", page_url),
                "renderer_type": renderer_type,
            },
        )

    @classmethod
    def parse_watch_initial_data(
        cls,
        url: str,
        yt_data: dict[str, Any],
        ytdlp_info: dict[str, Any] | None = None,
    ) -> CrawlResult:
        ytdlp_info = ytdlp_info or {}
        primary = cls._first_renderer(yt_data, "videoPrimaryInfoRenderer") or {}
        secondary = cls._first_renderer(yt_data, "videoSecondaryInfoRenderer") or {}
        owner = (
            secondary.get("owner", {})
            .get("videoOwnerRenderer", {})
        )

        video_id = (
            yt_data.get("currentVideoEndpoint", {})
            .get("watchEndpoint", {})
            .get("videoId")
            or ytdlp_info.get("id")
            or cls._extract_video_id(url)
            or ""
        )
        canonical_url = f"{YOUTUBE_ORIGIN}/watch?v={video_id}" if video_id else url
        title = cls._text(primary.get("title")) or ytdlp_info.get("title")
        description_full = (
            cls._text(secondary.get("description"))
            or ytdlp_info.get("description")
            or ""
        )
        view_count_text = cls._text(
            primary.get("viewCount", {})
            .get("videoViewCountRenderer", {})
            .get("viewCount")
        ) or cls._count_text(ytdlp_info.get("view_count"), "views")
        like_count_text = cls._like_text(primary) or cls._count_text(
            ytdlp_info.get("like_count")
        )
        comment_count_text = cls._comment_count_text(yt_data) or cls._count_text(
            ytdlp_info.get("comment_count"), "comments"
        )
        published_text = cls._text(primary.get("dateText")) or ytdlp_info.get(
            "upload_date"
        )

        channel_name = cls._text(owner.get("title")) or ytdlp_info.get("channel")
        channel_url = cls._absolute_youtube_url(cls._endpoint_url(owner.get("navigationEndpoint", {}))) or ytdlp_info.get("channel_url")
        channel_handle = cls._channel_handle(channel_url) or ytdlp_info.get("uploader_id")
        channel_avatar = cls._last_thumbnail_url(owner.get("thumbnail")) or ytdlp_info.get(
            "channel_thumbnail"
        )
        subscriber_count_text = cls._text(owner.get("subscriberCountText"))
        subscriber_count = cls._parse_count(subscriber_count_text)
        channel_badges = cls._badges(owner.get("badges") or owner.get("ownerBadges"))

        hashtags = cls._hashtags(description_full, primary)
        chapters = cls._chapters(ytdlp_info)
        captions = {
            "manual": list((ytdlp_info.get("subtitles") or {}).keys()),
            "automatic": list((ytdlp_info.get("automatic_captions") or {}).keys()),
        }
        thumbnails = cls._thumbnail_urls({"thumbnails": ytdlp_info.get("thumbnails") or []})
        if not thumbnails and ytdlp_info.get("thumbnail"):
            thumbnails = [ytdlp_info["thumbnail"]]
        formats = ytdlp_info.get("formats") or []
        engagement_buttons = cls._engagement_buttons(primary)
        badges = cls._dedupe(channel_badges + cls._badges(primary.get("badges")))

        visible_data = {
            "title": title,
            "canonical_url": canonical_url,
            "video_id": video_id,
            "description_full": description_full,
            "hashtags": hashtags,
            "view_count_text": view_count_text,
            "view_count": cls._parse_count(view_count_text),
            "like_count_text": like_count_text,
            "like_count": cls._parse_count(like_count_text),
            "comment_count_text": comment_count_text,
            "comment_count": cls._parse_count(comment_count_text),
            "published_text": published_text,
            "channel_name": channel_name,
            "channel_handle": channel_handle,
            "channel_url": channel_url,
            "channel_avatar": channel_avatar,
            "subscriber_count_text": subscriber_count_text,
            "subscriber_count": subscriber_count,
            "channel_verified": cls._is_verified(channel_badges),
            "chapters": chapters,
            "transcript": [],
            "captions": captions,
            "thumbnails": thumbnails,
            "formats": formats,
            "badges": badges,
            "engagement_buttons": engagement_buttons,
        }

        return CrawlResult(
            platform="youtube",
            source_id=video_id,
            url=canonical_url,
            title=title,
            content=description_full,
            content_type="short" if "/shorts/" in url else "video",
            author_id=ytdlp_info.get("channel_id") or channel_handle,
            author_name=channel_name,
            author_username=channel_handle,
            author_url=channel_url,
            author_avatar=channel_avatar,
            like_count=visible_data["like_count"],
            comment_count=visible_data["comment_count"],
            view_count=visible_data["view_count"],
            thumbnail_url=thumbnails[-1] if thumbnails else ytdlp_info.get("thumbnail"),
            tags=ytdlp_info.get("tags") or hashtags,
            subtitles=[
                {"language": lang, "type": "manual"}
                for lang in captions["manual"]
            ]
            + [
                {"language": lang, "type": "automatic"}
                for lang in captions["automatic"]
            ],
            media=[
                {
                    "type": "video",
                    "url": canonical_url,
                    "duration": ytdlp_info.get("duration"),
                    "formats_available": len(formats),
                    "chapters": chapters,
                    "captions": captions,
                    "thumbnails": thumbnails,
                }
            ],
            published_at=cls._parse_upload_date(ytdlp_info.get("upload_date")),
            raw=yt_data,
            visible_data=visible_data,
            raw_sources={
                "yt_initial_data": yt_data,
                "ytdlp": ytdlp_info,
            },
            capture_meta=cls._capture_meta("youtube_visible_detail", canonical_url),
        )

    async def _new_page(self) -> Page:
        return await browser_manager.new_page(
            cookies_file=self.settings.youtube_cookies_file,
            locale="en-US",
            user_agent=YOUTUBE_USER_AGENT,
        )

    async def _goto_with_consent(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded")
        await self._handle_consent(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            # networkidle timeout is non-fatal — continue with whatever loaded
            pass

    async def _handle_consent(self, page: Page) -> None:
        selectors = [
            "button[aria-label='Accept all']",
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
            "ytd-button-renderer:has-text('Accept all')",
            "form[action*='consent.youtube.com/save'] button",
        ]
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=1500):
                    await button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    return
            except Exception:
                continue

    async def _scroll_for_items(self, page: Page, limit: int) -> None:
        previous_count = 0
        stale_rounds = 0
        for _ in range(8):
            current_count = await page.locator("ytd-video-renderer, ytd-reel-item-renderer").count()
            if current_count >= limit:
                return
            if current_count == previous_count:
                stale_rounds += 1
            else:
                stale_rounds = 0
            if stale_rounds >= 2:
                return
            previous_count = current_count
            await page.mouse.wheel(0, 2400)
            await asyncio.sleep(1)

    async def _expand_description(self, page: Page) -> None:
        selectors = [
            "#description tp-yt-paper-button#expand",
            "tp-yt-paper-button#expand",
            "ytd-text-inline-expander tp-yt-paper-button",
            "button:has-text('more')",
            "button:has-text('Show more')",
        ]
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=1500):
                    await button.click()
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                continue

    async def _yt_initial_data(self, page: Page) -> dict[str, Any] | None:
        try:
            return await page.evaluate("() => window.ytInitialData || null")
        except Exception:
            return None

    async def _dom_snapshot(self, page: Page) -> dict[str, Any]:
        try:
            return await page.evaluate(
                """
                () => ({
                    url: window.location.href,
                    title: document.title,
                    visibleText: document.body ? document.body.innerText.slice(0, 20000) : ""
                })
                """
            )
        except Exception as exc:
            return {"error": str(exc)}

    async def _get_comments_from_dom(
        self, video_id: str, limit: int
    ) -> list[CommentResult]:
        url = f"{YOUTUBE_ORIGIN}/watch?v={video_id}"
        page = await self._new_page()
        results: list[CommentResult] = []
        seen: set[str] = set()
        stale_rounds = 0

        try:
            await self._goto_with_consent(page, url)
            await page.mouse.wheel(0, 1800)
            await asyncio.sleep(1.5)

            for _ in range(10):
                await self._expand_comment_replies(page)
                data = await page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('ytd-comment-thread-renderer')).map((thread, index) => {
                        const root = thread.querySelector('ytd-comment-view-model, ytd-comment-renderer') || thread;
                        const content = root.querySelector('#content-text');
                        const author = root.querySelector('#author-text, #author-name a, h3 a');
                        const published = root.querySelector('#published-time-text, .published-time-text');
                        const likes = root.querySelector('#vote-count-middle, #vote-count-left');
                        const replyCount = thread.querySelector('#more-replies button, ytd-button-renderer#more-replies');
                        return {
                            index,
                            contentText: content ? content.innerText.trim() : '',
                            authorName: author ? author.innerText.trim() : '',
                            authorUrl: author ? author.href : null,
                            publishedText: published ? published.innerText.trim() : '',
                            likeCountText: likes ? likes.innerText.trim() : '',
                            replyCountText: replyCount ? replyCount.innerText.trim() : '',
                            rawText: thread.innerText.slice(0, 5000)
                        };
                    })
                    """
                )
                added = 0
                for row in data:
                    if not row.get("contentText"):
                        continue
                    stable_hash = hashlib.sha1(
                        (row.get("contentText") or "").encode("utf-8")
                    ).hexdigest()[:12]
                    comment_id = f"dom_{video_id}_{row.get('index')}_{stable_hash}"
                    if comment_id in seen:
                        continue
                    seen.add(comment_id)
                    position = len(results) + 1
                    results.append(
                        self._parse_dom_comment(row, comment_id, position, url, limit)
                    )
                    added += 1
                    if len(results) >= limit:
                        return results[:limit]

                if added == 0:
                    stale_rounds += 1
                else:
                    stale_rounds = 0
                if stale_rounds >= 2:
                    break
                await page.mouse.wheel(0, 2200)
                await asyncio.sleep(1.5)
        except Exception as exc:
            logger.warning(f"[YouTube visible] DOM comments failed: {exc}")
        finally:
            await browser_manager.close_context(page)

        return results[:limit]

    async def _expand_comment_replies(self, page: Page) -> None:
        try:
            buttons = page.locator(
                "ytd-button-renderer#more-replies button, "
                "button[aria-label*='repl'], button:has-text('replies'), "
                "button:has-text('reply')"
            )
            count = min(await buttons.count(), 5)
            for idx in range(count):
                try:
                    await buttons.nth(idx).click(timeout=1000)
                    await asyncio.sleep(0.3)
                except Exception:
                    continue
        except Exception:
            return

    @classmethod
    def _iter_video_renderers(cls, yt_data: dict[str, Any]) -> list[dict[str, Any]]:
        renderers = []
        for key in ("videoRenderer", "reelItemRenderer"):
            for renderer in cls._find_all_renderers(yt_data, key):
                renderers.append({"type": key, "renderer": renderer})
        return renderers

    @classmethod
    def _find_all_renderers(cls, value: Any, renderer_name: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(value, dict):
            if isinstance(value.get(renderer_name), dict):
                found.append(value[renderer_name])
            for child in value.values():
                found.extend(cls._find_all_renderers(child, renderer_name))
        elif isinstance(value, list):
            for child in value:
                found.extend(cls._find_all_renderers(child, renderer_name))
        return found

    @classmethod
    def _first_renderer(
        cls, value: Any, renderer_name: str
    ) -> dict[str, Any] | None:
        items = cls._find_all_renderers(value, renderer_name)
        return items[0] if items else None

    @staticmethod
    def _first_run(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            runs = value.get("runs")
            if isinstance(runs, list) and runs:
                return runs[0]
        return {}

    @classmethod
    def _text(cls, value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(cls._text(item) for item in value)
        if isinstance(value, dict):
            if isinstance(value.get("simpleText"), str):
                return value["simpleText"]
            if isinstance(value.get("text"), str):
                return value["text"]
            runs = value.get("runs")
            if isinstance(runs, list):
                return "".join(run.get("text", "") for run in runs)
            overlays = value.get("thumbnailOverlayTimeStatusRenderer")
            if overlays:
                return cls._text(overlays.get("text"))
            for child in value.values():
                text = cls._text(child)
                if text:
                    return text
        return ""

    @staticmethod
    def _endpoint_url(endpoint: dict[str, Any]) -> str | None:
        if not endpoint:
            return None
        metadata_url = (
            endpoint.get("commandMetadata", {})
            .get("webCommandMetadata", {})
            .get("url")
        )
        if metadata_url:
            return metadata_url
        if endpoint.get("watchEndpoint", {}).get("videoId"):
            return f"/watch?v={endpoint['watchEndpoint']['videoId']}"
        if endpoint.get("browseEndpoint", {}).get("canonicalBaseUrl"):
            return endpoint["browseEndpoint"]["canonicalBaseUrl"]
        return None

    @staticmethod
    def _absolute_youtube_url(url: str | None) -> str | None:
        if not url:
            return None
        return urljoin(YOUTUBE_ORIGIN, url)

    @classmethod
    def _video_url(
        cls, video_id: str | None, endpoint_url: str | None, is_short: bool = False
    ) -> str | None:
        if endpoint_url:
            absolute = cls._absolute_youtube_url(endpoint_url)
            if absolute:
                return absolute
        if not video_id:
            return None
        path = "shorts" if is_short else "watch"
        return (
            f"{YOUTUBE_ORIGIN}/{path}/{video_id}"
            if is_short
            else f"{YOUTUBE_ORIGIN}/watch?v={video_id}"
        )

    @staticmethod
    def _channel_handle(channel_url: str | None) -> str | None:
        if not channel_url:
            return None
        path = urlparse(channel_url).path.strip("/")
        if not path:
            return None
        last = path.split("/")[-1]
        return last if last.startswith("@") else last

    @staticmethod
    def _extract_video_id(url: str | None) -> str | None:
        if not url:
            return None
        if re.fullmatch(r"[\w-]{8,}", url):
            return url
        parsed = urlparse(urljoin(YOUTUBE_ORIGIN, url))
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else None
        query_id = parse_qs(parsed.query).get("v")
        if query_id:
            return query_id[0]
        match = re.search(r"(?:youtu\.be/|/embed/)([\w-]+)", url)
        return match.group(1) if match else None

    @staticmethod
    def _thumbnail_urls(thumbnail: Any) -> list[str]:
        thumbnails = []
        if isinstance(thumbnail, dict):
            thumbnails = thumbnail.get("thumbnails") or []
        elif isinstance(thumbnail, list):
            thumbnails = thumbnail
        urls = [item.get("url") for item in thumbnails if item.get("url")]
        return [url for url in urls if url]

    @classmethod
    def _last_thumbnail_url(cls, thumbnail: Any) -> str | None:
        urls = cls._thumbnail_urls(thumbnail)
        return urls[-1] if urls else None

    @staticmethod
    def _parse_duration(text: str | None) -> int | None:
        if not text:
            return None
        parts = [part for part in text.strip().split(":") if part.isdigit()]
        if not parts:
            return None
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds

    @staticmethod
    def _parse_count(text: str | int | None) -> int:
        if text is None:
            return 0
        if isinstance(text, int):
            return text
        normalized = str(text).lower().replace(",", "")
        normalized = normalized.replace("views", "").replace("view", "")
        normalized = normalized.replace("subscribers", "").replace("subscriber", "")
        normalized = normalized.replace("comments", "").replace("comment", "")
        normalized = normalized.strip()
        match = re.search(r"([\d.]+)\s*([kmb]?)", normalized)
        if not match:
            return 0
        value = float(match.group(1))
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
            match.group(2), 1
        )
        return int(value * multiplier)

    @staticmethod
    def _count_text(count: int | None, suffix: str | None = None) -> str:
        if count is None:
            return ""
        return f"{count:,} {suffix}".strip() if suffix else f"{count:,}"

    @classmethod
    def _badges(cls, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, dict):
            value = [value]
        badges = []
        if not isinstance(value, list):
            return badges
        for item in value:
            renderer = item.get("metadataBadgeRenderer", item) if isinstance(item, dict) else {}
            label = (
                renderer.get("label")
                or renderer.get("tooltip")
                or renderer.get("accessibilityData", {}).get("label")
                or renderer.get("style")
            )
            if label:
                badges.append(label)
        return cls._dedupe(badges)

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen = set()
        result = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @staticmethod
    def _is_verified(badges: list[str]) -> bool:
        return any("verified" in badge.lower() for badge in badges)

    @classmethod
    def _description_snippet(cls, renderer: dict[str, Any]) -> str:
        snippets = renderer.get("detailedMetadataSnippets") or []
        for snippet in snippets:
            text = cls._text(snippet.get("snippetText"))
            if text:
                return text
        return cls._text(renderer.get("descriptionSnippet"))

    @classmethod
    def _like_text(cls, primary: dict[str, Any]) -> str:
        buttons = (
            primary.get("videoActions", {})
            .get("menuRenderer", {})
            .get("topLevelButtons", [])
        )
        for button in buttons:
            segmented = button.get("segmentedLikeDislikeButtonRenderer", {})
            like_renderer = (
                segmented.get("likeButton", {}).get("toggleButtonRenderer", {})
                or button.get("toggleButtonRenderer", {})
            )
            text = cls._text(
                like_renderer.get("defaultText")
                or like_renderer.get("toggledText")
                or like_renderer.get("accessibilityData")
            )
            if text:
                return text
        return ""

    @classmethod
    def _comment_count_text(cls, yt_data: dict[str, Any]) -> str:
        header = cls._first_renderer(yt_data, "commentsHeaderRenderer") or {}
        return cls._text(header.get("countText"))

    @classmethod
    def _engagement_buttons(cls, primary: dict[str, Any]) -> list[dict[str, str]]:
        buttons = (
            primary.get("videoActions", {})
            .get("menuRenderer", {})
            .get("topLevelButtons", [])
        )
        results = []
        for button in buttons:
            label = cls._text(button)
            if label:
                results.append({"label": label})
        return results

    @classmethod
    def _hashtags(cls, description: str, primary: dict[str, Any]) -> list[str]:
        hashtags = re.findall(r"#[\w\u4e00-\u9fff-]+", description or "")
        super_title = primary.get("superTitleLink") or {}
        for run in super_title.get("runs", []) if isinstance(super_title, dict) else []:
            text = run.get("text", "")
            if text.startswith("#"):
                hashtags.append(text)
        return cls._dedupe(hashtags)

    @staticmethod
    def _chapters(ytdlp_info: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "start_time": chapter.get("start_time"),
                "end_time": chapter.get("end_time"),
                "title": chapter.get("title"),
            }
            for chapter in (ytdlp_info.get("chapters") or [])
        ]

    @staticmethod
    def _parse_upload_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _parse_ytdlp_info(
        cls, info: dict[str, Any], method: str
    ) -> CrawlResult:
        url = (
            info.get("original_url")
            or info.get("webpage_url")
            or f"{YOUTUBE_ORIGIN}/watch?v={info.get('id')}"
        )
        visible_data = {
            "title": info.get("title"),
            "canonical_url": url,
            "video_id": info.get("id"),
            "description_full": info.get("description"),
            "hashtags": [
                tag if str(tag).startswith("#") else f"#{tag}"
                for tag in (info.get("tags") or [])
                if tag
            ],
            "view_count_text": cls._count_text(info.get("view_count"), "views"),
            "view_count": info.get("view_count") or 0,
            "like_count_text": cls._count_text(info.get("like_count")),
            "like_count": info.get("like_count") or 0,
            "comment_count_text": cls._count_text(info.get("comment_count"), "comments"),
            "comment_count": info.get("comment_count") or 0,
            "published_text": info.get("upload_date"),
            "channel_name": info.get("channel") or info.get("uploader"),
            "channel_handle": info.get("uploader_id"),
            "channel_url": info.get("channel_url"),
            "channel_avatar": info.get("channel_thumbnail"),
            "subscriber_count_text": cls._count_text(
                info.get("channel_follower_count"), "subscribers"
            ),
            "subscriber_count": info.get("channel_follower_count") or 0,
            "channel_verified": bool(info.get("channel_is_verified")),
            "chapters": cls._chapters(info),
            "transcript": [],
            "captions": {
                "manual": list((info.get("subtitles") or {}).keys()),
                "automatic": list((info.get("automatic_captions") or {}).keys()),
            },
            "thumbnails": cls._thumbnail_urls({"thumbnails": info.get("thumbnails") or []})
            or ([info.get("thumbnail")] if info.get("thumbnail") else []),
            "formats": info.get("formats") or [],
            "badges": [],
            "engagement_buttons": [],
        }
        return CrawlResult(
            platform="youtube",
            source_id=info.get("id", ""),
            url=url,
            title=info.get("title"),
            content=info.get("description"),
            content_type="short" if "/shorts/" in url else "video",
            author_id=info.get("channel_id"),
            author_name=visible_data["channel_name"],
            author_username=visible_data["channel_handle"],
            author_url=info.get("channel_url"),
            like_count=visible_data["like_count"],
            comment_count=visible_data["comment_count"],
            view_count=visible_data["view_count"],
            thumbnail_url=info.get("thumbnail"),
            tags=info.get("tags") or [],
            media=[
                {
                    "type": "video",
                    "url": url,
                    "duration": info.get("duration"),
                    "formats_available": len(info.get("formats") or []),
                    "chapters": visible_data["chapters"],
                    "captions": visible_data["captions"],
                    "thumbnails": visible_data["thumbnails"],
                }
            ],
            published_at=cls._parse_upload_date(info.get("upload_date")),
            raw=info,
            visible_data=visible_data,
            raw_sources={"ytdlp": info},
            capture_meta=cls._capture_meta(method, url),
        )

    @classmethod
    def _parse_ytdlp_comment(
        cls,
        raw: dict[str, Any],
        position: int,
        video_id: str,
        limit: int,
    ) -> CommentResult:
        comment_id = raw.get("id") or f"ytdlp_{video_id}_{position}"
        published_at = None
        if raw.get("timestamp"):
            try:
                published_at = datetime.fromtimestamp(raw["timestamp"], tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                published_at = None
        author_handle = raw.get("author_id") or raw.get("author")
        visible_data = {
            "comment_id": comment_id,
            "parent_comment_id": raw.get("parent"),
            "thread_position": position,
            "is_reply": bool(raw.get("parent")),
            "author_name": raw.get("author"),
            "author_handle": author_handle,
            "author_url": raw.get("author_url"),
            "author_avatar": raw.get("author_thumbnail"),
            "author_badges": [],
            "content_text": raw.get("text") or "",
            "published_text": raw.get("time_text") or "",
            "like_count_text": cls._count_text(raw.get("like_count")),
            "like_count": raw.get("like_count") or 0,
            "reply_count_text": cls._count_text(raw.get("reply_count")),
            "reply_count": raw.get("reply_count") or 0,
            "is_pinned": bool(raw.get("is_pinned")),
            "is_creator_hearted": bool(raw.get("is_favorited")),
            "is_author_owner": bool(raw.get("author_is_uploader")),
        }
        return CommentResult(
            platform="youtube",
            source_id=comment_id,
            content=visible_data["content_text"],
            author_name=visible_data["author_name"],
            author_username=author_handle,
            author_id=raw.get("author_id"),
            like_count=visible_data["like_count"],
            reply_count=visible_data["reply_count"],
            parent_comment_id=visible_data["parent_comment_id"],
            published_at=published_at,
            raw=raw,
            visible_data=visible_data,
            raw_sources={"ytdlp": raw},
            capture_meta=cls._capture_meta(
                "youtube_ytdlp_comments",
                f"{YOUTUBE_ORIGIN}/watch?v={video_id}",
                limit=limit,
            ),
        )

    @classmethod
    def _parse_dom_comment(
        cls,
        row: dict[str, Any],
        comment_id: str,
        position: int,
        url: str,
        limit: int,
    ) -> CommentResult:
        like_count_text = row.get("likeCountText") or ""
        author_url = row.get("authorUrl")
        author_handle = cls._channel_handle(author_url)
        visible_data = {
            "comment_id": comment_id,
            "parent_comment_id": None,
            "thread_position": position,
            "is_reply": False,
            "author_name": row.get("authorName") or "",
            "author_handle": author_handle,
            "author_url": author_url,
            "author_avatar": None,
            "author_badges": [],
            "content_text": row.get("contentText") or "",
            "published_text": row.get("publishedText") or "",
            "like_count_text": like_count_text,
            "like_count": cls._parse_count(like_count_text),
            "reply_count_text": row.get("replyCountText") or "",
            "reply_count": cls._parse_count(row.get("replyCountText") or ""),
            "is_pinned": "pinned" in (row.get("rawText") or "").lower(),
            "is_creator_hearted": False,
            "is_author_owner": False,
        }
        return CommentResult(
            platform="youtube",
            source_id=comment_id,
            content=visible_data["content_text"],
            author_name=visible_data["author_name"],
            author_username=author_handle,
            like_count=visible_data["like_count"],
            reply_count=visible_data["reply_count"],
            published_at=datetime.now(timezone.utc),
            raw=row,
            visible_data=visible_data,
            raw_sources={"dom_snapshot": row},
            capture_meta=cls._capture_meta(
                "youtube_visible_dom_comments",
                url,
                limit=limit,
            ),
        )

    @staticmethod
    def _capture_meta(
        method: str,
        url: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "method": method,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
        }
        if limit is not None:
            meta["limit"] = limit
        settings = get_settings()
        meta["cookies_file_configured"] = bool(settings.youtube_cookies_file)
        return meta

    async def close(self) -> None:
        pass
