"""
Reddit crawler — captures every piece of publicly visible data.

Data captured per post:
  - Full post metadata: title, body, subreddit, score, upvote_ratio,
    num_comments, awards, flair (author + post), crosspost chain,
    domain, content_type, nsfw, spoiler, stickied, pinned,
    distinguished, edited, locked, is_self, link_url, permalink,
    created_utc, all media (images / videos / galleries / reddit videos)
  - Author profile: karma totals, account age, verified, is_gold,
    description, icon, trophies
  - Subreddit info: title, subscribers, active_users, description,
    type, nsfw, created_utc, rules
  - Full recursive comment tree: every reply at every depth, with
    author, score, body_html, awards, distinguished, edited, stickied,
    flair — plus automatic expansion of "load more" nodes

Usage:
  crawler = RedditCrawler()
  results = await crawler.search("python", limit=10)
  detail  = await crawler.get_post_detail(url)
  comments = await crawler.get_comments(post_id, limit=500)
"""

import re
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from app.crawlers.base import BaseCrawler, CommentResult, CrawlResult
from app.crawlers.reddit.api_client import RedditAPIClient

# ══════════════════════════════════════════════════════════════════════════════
#   Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _ts(unix: Any) -> datetime | None:
    """Convert a Unix timestamp to a UTC-aware datetime."""
    try:
        return datetime.fromtimestamp(float(unix), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _award_list(data: dict) -> list[dict]:
    """Extract a compact award list from a post / comment dict."""
    awards = []
    for a in data.get("all_awardings") or []:
        awards.append(
            {
                "name": a.get("name"),
                "count": a.get("count", 1),
                "icon_url": a.get("icon_url"),
                "coin_price": a.get("coin_price"),
                "description": a.get("description"),
            }
        )
    return awards


def _media_from_post(data: dict) -> list[dict]:
    """
    Extract all media items from a Reddit post dict.
    Handles: reddit videos, images, galleries, external links,
             preview images, and rich video embeds.
    """
    media_list: list[dict] = []

    # ── Reddit native video ────────────────────────────────
    reddit_video = (data.get("media") or {}).get("reddit_video")
    if reddit_video:
        media_list.append(
            {
                "type": "video",
                "source": "reddit_video",
                "url": reddit_video.get("fallback_url"),
                "hls_url": reddit_video.get("hls_url"),
                "dash_url": reddit_video.get("dash_url"),
                "width": reddit_video.get("width"),
                "height": reddit_video.get("height"),
                "duration": reddit_video.get("duration"),
                "is_gif": reddit_video.get("is_gif", False),
            }
        )

    # ── Gallery ────────────────────────────────────────────
    if data.get("is_gallery") and data.get("gallery_data"):
        media_metadata = data.get("media_metadata") or {}
        for item in data["gallery_data"].get("items", []):
            mid = item.get("media_id", "")
            meta = media_metadata.get(mid, {})
            status = meta.get("status", "")
            if status != "valid":
                continue
            mime = meta.get("m", "")
            is_video = mime.startswith("video")
            src = meta.get("s", {})
            entry: dict = {
                "type": "video" if is_video else "image",
                "source": "gallery",
                "media_id": mid,
                "caption": item.get("caption"),
                "outbound_url": item.get("outbound_url"),
                "mime_type": mime,
            }
            if is_video:
                entry["url"] = src.get("mp4") or src.get("gif")
                entry["width"] = src.get("x")
                entry["height"] = src.get("y")
            else:
                entry["url"] = src.get("u", "").replace("&amp;", "&")
                entry["width"] = src.get("x")
                entry["height"] = src.get("y")
                # Include resized previews
                entry["previews"] = [
                    {
                        "url": p.get("u", "").replace("&amp;", "&"),
                        "width": p.get("x"),
                        "height": p.get("y"),
                    }
                    for p in meta.get("p", [])
                ]
            media_list.append(entry)

    # ── Single image / preview ─────────────────────────────
    if not media_list:
        hint = data.get("post_hint", "")
        url = data.get("url", "")

        if hint == "image" or url.lower().split("?")[0].endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        ):
            entry: dict = {"type": "image", "source": "direct", "url": url}
            preview = (data.get("preview") or {}).get("images", [])
            if preview:
                src = preview[0].get("source", {})
                entry["width"] = src.get("width")
                entry["height"] = src.get("height")
                entry["previews"] = [
                    {
                        "url": r.get("url", "").replace("&amp;", "&"),
                        "width": r.get("width"),
                        "height": r.get("height"),
                    }
                    for r in preview[0].get("resolutions", [])
                ]
            media_list.append(entry)

        elif hint in ("link", "rich:video", "hosted:video"):
            # Embedded / external video
            oembed = (data.get("media") or {}).get("oembed", {})
            entry = {
                "type": "video",
                "source": "external",
                "url": url,
                "provider": oembed.get("provider_name"),
                "thumbnail_url": oembed.get("thumbnail_url"),
                "width": oembed.get("width"),
                "height": oembed.get("height"),
                "html": oembed.get("html"),
            }
            media_list.append(entry)

    # ── Thumbnail (always include if present) ──────────────
    thumb = data.get("thumbnail", "")
    if (
        thumb
        and thumb.startswith("http")
        and not any(m.get("source") == "direct" for m in media_list)
    ):
        media_list.append({"type": "thumbnail", "source": "thumbnail", "url": thumb})

    return media_list


def _flair(data: dict, prefix: str) -> str | None:
    """Build a readable flair string from richtext or plain text fields."""
    # richtext flair
    richtext = data.get(f"{prefix}_flair_richtext") or []
    text_parts = [r.get("t", "") for r in richtext if r.get("e") == "text" and r.get("t")]
    if text_parts:
        return " ".join(text_parts).strip() or None
    # plain text
    return data.get(f"{prefix}_flair_text") or None


def _crosspost_chain(data: dict) -> list[dict]:
    """Extract the crosspost parent chain (if any)."""
    chain = []
    for cp in data.get("crosspost_parent_list") or []:
        chain.append(
            {
                "post_id": cp.get("id"),
                "subreddit": cp.get("subreddit"),
                "title": cp.get("title"),
                "url": f"https://www.reddit.com{cp.get('permalink', '')}",
                "score": cp.get("score", 0),
            }
        )
    return chain


def _extract_post_ids(url: str) -> tuple[str, str]:
    """Extract (subreddit, post_id) from a Reddit URL."""
    match = re.search(r"(?:old\.)?reddit\.com/r/([A-Za-z0-9_-]+)/comments/([A-Za-z0-9_]+)", url)
    if match:
        return match.group(1), match.group(2)
    # Try short-form /comments/post_id
    match = re.search(r"/comments/([\w]+)", url)
    if match:
        return "all", match.group(1)
    raise ValueError(f"Cannot parse Reddit URL: {url}")


# ══════════════════════════════════════════════════════════════════════════════
#   Main crawler
# ══════════════════════════════════════════════════════════════════════════════


class RedditCrawler(BaseCrawler):
    """
    Reddit platform crawler.
    Captures all publicly visible post, author, subreddit, and comment data.
    """

    platform = "reddit"

    @staticmethod
    def _extract_post_info(url: str) -> tuple[str, str]:
        """Backward-compatible URL parser used by tests and older callers."""
        return _extract_post_ids(url)

    def __init__(self):
        super().__init__()
        self.api = RedditAPIClient()

        # Cache subreddit info to avoid redundant API calls
        self._subreddit_cache: dict[str, dict] = {}
        # Cache user info similarly
        self._user_cache: dict[str, dict] = {}

    # ────────────────────────────────────────────────── public interface

    async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
        """Search Reddit posts by keyword with full metadata. Uses time-slicing for massive data retrieval."""
        await self._rate_limit()
        logger.info(f"[Reddit] Search: '{keyword}', limit={limit}")

        if limit <= 100:
            # Quick standard search for low limits
            return await self._search_batch(keyword, limit)

        # Time-sliced search for high-concurrency / massive data ingestion
        import time
        now = int(time.time())
        day_seconds = 86400
        
        # We slice into weekly segments (7 days) going backwards in time
        slice_days = 7
        slice_seconds = slice_days * day_seconds
        current_end = now
        total_slices = 24  # Look back up to ~6 months
        
        results: list[CrawlResult] = []
        for _ in range(total_slices):
            if len(results) >= limit:
                break
                
            current_start = current_end - slice_seconds
            time_query = f"{keyword} timestamp:{current_start}..{current_end}"
            logger.info(f"[Reddit Slicer] Searching slice {current_start} to {current_end} ({slice_days} days)")
            
            slice_limit = min(limit - len(results), 500)
            slice_results = await self._search_batch(time_query, slice_limit, syntax="cloudsearch")
            results.extend(slice_results)
            
            current_end = current_start
            
            # Simple break if we have reached limit
            if not slice_results and len(results) == 0:
                # If we get absolutely nothing in the most recent slice, let's keep looking back slightly
                # but if we get nothing after multiple iterations, we can safely break.
                continue

        logger.info(f"[Reddit Slicer] Completed search, gathered {len(results)} total results")
        return results[:limit]

    async def _search_batch(self, query: str, limit: int, **kwargs) -> list[CrawlResult]:
        """Perform a single standard search batch with pagination."""
        results: list[CrawlResult] = []
        after: str | None = None
        remaining = limit

        while remaining > 0:
            batch = min(remaining, 100)
            try:
                response = await self.api.search(query=query, limit=batch, after=after, **kwargs)
                data = response.get("data", {})
                children = data.get("children", [])
                if not children:
                    break
                for child in children:
                    results.append(await self._parse_post(child.get("data", {}), fetch_extras=False))
                remaining -= len(children)
                after = data.get("after")
                if not after:
                    break
            except Exception as e:
                logger.error(f"[Reddit Slicer] Search batch failed: {e}")
                break

        return results

    async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
        """Get all posts from a Reddit user with full metadata."""
        await self._rate_limit()
        logger.info(f"[Reddit] User posts: u/{username}, limit={limit}")

        results: list[CrawlResult] = []
        after: str | None = None
        remaining = limit

        while remaining > 0:
            batch = min(remaining, 100)
            response = await self.api.get_user_posts(username, limit=batch, after=after)
            data = response.get("data", {})
            children = data.get("children", [])
            if not children:
                break
            for child in children:
                results.append(await self._parse_post(child.get("data", {}), fetch_extras=False))
            remaining -= len(children)
            after = data.get("after")
            if not after:
                break

        return results[:limit]

    async def get_post_detail(self, url: str) -> CrawlResult:
        """
        Get complete details for a single Reddit post.
        Also fetches: author profile, subreddit info.
        """
        await self._rate_limit()
        subreddit, post_id = _extract_post_ids(url)
        logger.info(f"[Reddit] Post detail: r/{subreddit}/{post_id}")

        response = await self.api.get_post_detail(subreddit, post_id)

        # Response is [post_listing, comments_listing]
        if isinstance(response, list) and response:
            children = response[0].get("data", {}).get("children", [])
            if children:
                return await self._parse_post(children[0].get("data", {}), fetch_extras=True)

        raise ValueError(f"Could not parse post from: {url}")

    async def get_comments(self, post_id: str, limit: int = 500) -> list[CommentResult]:
        """
        Get the full comment tree for a post.

        Automatically expands all 'MoreComments' (load-more) nodes until
        `limit` is reached. The result is a flat list preserving reply
        relationships via parent_comment_id.
        """
        await self._rate_limit()
        logger.info(f"[Reddit] Comments: {post_id}, limit={limit}")

        # post_id may arrive as "subreddit:id" or bare id
        if ":" in post_id:
            subreddit, pid = post_id.split(":", 1)
        else:
            subreddit, pid = "all", post_id

        response = await self.api.get_comments(subreddit, pid, sort="best", limit=min(limit, 500))

        results: list[CommentResult] = []
        if not isinstance(response, list) or len(response) < 2:
            return results

        post_fullname = f"t3_{pid}"
        comments_listing = response[1]
        children = comments_listing.get("data", {}).get("children", [])

        await self._expand_comments(
            children=children,
            results=results,
            post_fullname=post_fullname,
            parent_id=None,
            limit=limit,
        )

        logger.info(f"[Reddit] Collected {len(results)} comments (incl. replies)")
        return results[:limit]

    # ────────────────────────────────────────────────── comment tree

    async def _expand_comments(
        self,
        children: list[dict],
        results: list[CommentResult],
        post_fullname: str,
        parent_id: str | None,
        limit: int,
    ) -> None:
        """
        Recursively parse comment tree, automatically expanding
        'more' nodes by calling the morechildren API.
        """
        more_ids: list[str] = []

        for child in children:
            if len(results) >= limit:
                break

            kind = child.get("kind")
            data = child.get("data", {})

            if kind == "t1":
                # Real comment
                comment = self._parse_comment(data, parent_id)
                results.append(comment)

                # Recurse into replies
                replies_data = data.get("replies")
                if isinstance(replies_data, dict):
                    reply_children = replies_data.get("data", {}).get("children", [])
                    await self._expand_comments(
                        reply_children,
                        results,
                        post_fullname,
                        parent_id=comment.source_id,
                        limit=limit,
                    )

            elif kind == "more":
                # "Load more comments" node — collect IDs for batch expansion
                ids = data.get("children") or []
                more_ids.extend(ids)

        # Expand collected "more" IDs in batches of 100
        for i in range(0, len(more_ids), 100):
            if len(results) >= limit:
                break
            batch = more_ids[i : i + 100]
            try:
                more_resp = await self.api.get_more_children(post_fullname, batch, sort="best")
                more_things = more_resp.get("json", {}).get("data", {}).get("things", [])
                await self._expand_comments(
                    more_things,
                    results,
                    post_fullname,
                    parent_id=parent_id,
                    limit=limit,
                )
            except Exception as e:
                logger.warning(f"[Reddit] morechildren expansion failed: {e}")

    # ────────────────────────────────────────────────── parsers

    async def _parse_post(self, data: dict, fetch_extras: bool = False) -> CrawlResult:
        """Parse a Reddit post dict into a fully-populated CrawlResult."""

        post_id = data.get("id", "")
        permalink = data.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else data.get("url", "")
        link_url = data.get("url", "")  # may be same as url for self-posts

        subreddit = data.get("subreddit", "")
        is_self = bool(data.get("is_self"))

        # ── content type ──────────────────────────────
        if data.get("is_video"):
            content_type = "video"
        elif data.get("is_gallery"):
            content_type = "gallery"
        elif data.get("post_hint") == "image":
            content_type = "image"
        elif data.get("post_hint") in ("rich:video", "hosted:video"):
            content_type = "video"
        elif is_self:
            content_type = "text"
        else:
            content_type = "link"

        # ── author ───────────────────────────────────
        author_name = data.get("author", "")
        author_info = await self._get_user_info(author_name) if fetch_extras else {}

        # ── subreddit ────────────────────────────────
        sub_info = await self._get_subreddit_info(subreddit) if fetch_extras else {}

        # ── awards ───────────────────────────────────
        awards = _award_list(data)

        # ── flair ────────────────────────────────────
        post_flair = _flair(data, "link")
        author_flair = _flair(data, "author")

        # ── media ────────────────────────────────────
        media = _media_from_post(data)

        # ── visible_data: every field visible on screen ──
        visible_data = {
            # identity
            "post_id": post_id,
            "subreddit": subreddit,
            "subreddit_id": data.get("subreddit_id"),
            "subreddit_type": data.get("subreddit_type"),
            "permalink": url,
            "link_url": link_url if not is_self else None,
            "domain": data.get("domain"),
            "is_self": is_self,
            "content_type": content_type,
            # text
            "title": data.get("title"),
            "body": data.get("selftext") or "",
            "body_html": data.get("selftext_html") or "",
            # engagement
            "score": data.get("score", 0),
            "upvote_ratio": data.get("upvote_ratio"),
            "ups": data.get("ups", 0),
            "downs": data.get("downs", 0),
            "num_comments": data.get("num_comments", 0),
            "num_crossposts": data.get("num_crossposts", 0),
            "num_reports": data.get("num_reports"),
            # awards
            "total_awards_received": data.get("total_awards_received", 0),
            "gilded": data.get("gilded", 0),
            "awards": awards,
            # flair
            "post_flair": post_flair,
            "post_flair_css_class": data.get("link_flair_css_class"),
            "author_flair": author_flair,
            "author_flair_css_class": data.get("author_flair_css_class"),
            # flags
            "nsfw": bool(data.get("over_18")),
            "spoiler": bool(data.get("spoiler")),
            "stickied": bool(data.get("stickied")),
            "pinned": bool(data.get("pinned")),
            "locked": bool(data.get("locked")),
            "archived": bool(data.get("archived")),
            "quarantine": bool(data.get("quarantine")),
            "edited": data.get("edited"),  # False or timestamp
            "distinguished": data.get("distinguished"),  # None | "moderator" | "admin"
            "is_crosspostable": bool(data.get("is_crosspostable")),
            "crosspost_chain": _crosspost_chain(data),
            # media
            "media": media,
            "thumbnail": data.get("thumbnail"),
            # author
            "author_name": author_name,
            "author_fullname": data.get("author_fullname"),
            "author_is_blocked": bool(data.get("author_is_blocked")),
            "author_profile": author_info,
            # subreddit
            "subreddit_info": sub_info,
            # timestamps
            "created_utc": data.get("created_utc"),
        }

        return CrawlResult(
            platform="reddit",
            source_id=post_id,
            url=url,
            title=data.get("title"),
            content=data.get("selftext") or "",
            content_type=content_type,
            author_id=data.get("author_fullname"),
            author_name=author_name,
            author_username=author_name,
            author_url=f"https://www.reddit.com/user/{author_name}" if author_name else None,
            like_count=data.get("score", 0),
            comment_count=data.get("num_comments", 0),
            share_count=data.get("num_crossposts", 0),
            view_count=0,
            media=media,
            thumbnail_url=(
                data.get("thumbnail") if str(data.get("thumbnail", "")).startswith("http") else None
            ),
            tags=[],
            published_at=_ts(data.get("created_utc")),
            raw=data,
            visible_data=visible_data,
            raw_sources={"reddit_api": data},
        )

    def _parse_comment(self, data: dict, parent_comment_id: str | None) -> CommentResult:
        """Parse a Reddit comment dict into a fully-populated CommentResult."""

        comment_id = data.get("id", "")
        author = data.get("author", "")
        body = data.get("body", "")

        awards = _award_list(data)
        author_flair = _flair(data, "author")

        edited = data.get("edited")  # False or Unix timestamp
        edited_at = _ts(edited) if isinstance(edited, (int, float)) else None

        visible_data = {
            "comment_id": comment_id,
            "post_id": data.get("link_id", ""),
            "subreddit": data.get("subreddit", ""),
            "parent_id": data.get("parent_id", ""),  # t1_xxx or t3_xxx
            "parent_comment_id": parent_comment_id,
            "depth": data.get("depth", 0),
            # content
            "body": body,
            "body_html": data.get("body_html", ""),
            # author
            "author": author,
            "author_fullname": data.get("author_fullname"),
            "author_flair": author_flair,
            "author_flair_css_class": data.get("author_flair_css_class"),
            "author_is_submitter": bool(data.get("is_submitter")),
            # engagement
            "score": data.get("score", 0),
            "ups": data.get("ups", 0),
            "downs": data.get("downs", 0),
            "controversiality": data.get("controversiality", 0),
            "gilded": data.get("gilded", 0),
            "total_awards_received": data.get("total_awards_received", 0),
            "awards": awards,
            # flags
            "stickied": bool(data.get("stickied")),
            "saved": bool(data.get("saved")),
            "locked": bool(data.get("locked")),
            "collapsed": bool(data.get("collapsed")),
            "distinguished": data.get("distinguished"),
            "edited": bool(data.get("edited")),
            "edited_at": edited_at.isoformat() if edited_at else None,
            "score_hidden": bool(data.get("score_hidden")),
            # timestamps
            "created_utc": data.get("created_utc"),
        }

        return CommentResult(
            platform="reddit",
            source_id=comment_id,
            content=body,
            author_name=author,
            author_username=author,
            author_id=data.get("author_fullname"),
            like_count=data.get("score", 0),
            reply_count=0,  # Reddit API doesn't expose reply count directly
            parent_comment_id=parent_comment_id,
            published_at=_ts(data.get("created_utc")),
            raw=data,
            visible_data=visible_data,
            raw_sources={"reddit_api": data},
        )

    # ────────────────────────────────────────────────── info helpers

    async def _get_user_info(self, username: str) -> dict:
        """
        Fetch and cache a user's public profile data.
        Returns an empty dict for deleted/suspended accounts.
        """
        if not username or username in ("[deleted]", "[removed]"):
            return {}
        if username in self._user_cache:
            return self._user_cache[username]

        try:
            resp = await self.api.get_user_info(username)
            udata = resp.get("data", {})

            # Trophies (best-effort)
            trophies: list[str] = []
            try:
                trophy_resp = await self.api.get_user_trophies(username)
                trophy_list = trophy_resp.get("data", {}).get("trophies", [])
                trophies = [
                    t.get("data", {}).get("name", "")
                    for t in trophy_list
                    if t.get("data", {}).get("name")
                ]
            except Exception:
                pass  # Non-critical

            profile = {
                "username": udata.get("name"),
                "fullname": udata.get("id"),
                "created_utc": udata.get("created_utc"),
                "link_karma": udata.get("link_karma", 0),
                "comment_karma": udata.get("comment_karma", 0),
                "total_karma": udata.get("total_karma", 0),
                "icon_img": udata.get("icon_img"),
                "snoovatar_img": udata.get("snoovatar_img"),
                "is_gold": bool(udata.get("is_gold")),
                "is_mod": bool(udata.get("is_mod")),
                "verified": bool(udata.get("verified")),
                "has_verified_email": bool(udata.get("has_verified_email")),
                "is_employee": bool(udata.get("is_employee")),
                "hide_from_robots": bool(udata.get("hide_from_robots")),
                "description": (udata.get("subreddit") or {}).get("public_description", ""),
                "accept_followers": bool(udata.get("accept_followers")),
                "trophies": trophies,
            }
            self._user_cache[username] = profile
            return profile
        except Exception as e:
            logger.debug(f"[Reddit] Could not fetch user info for u/{username}: {e}")
            return {}

    async def _get_subreddit_info(self, subreddit: str) -> dict:
        """Fetch and cache subreddit metadata."""
        if not subreddit:
            return {}
        if subreddit in self._subreddit_cache:
            return self._subreddit_cache[subreddit]

        try:
            resp = await self.api.get_subreddit_info(subreddit)
            sdata = resp.get("data", {})

            # Rules (best-effort)
            rules: list[dict] = []
            try:
                rules_resp = await self.api.get_subreddit_rules(subreddit)
                for rule in rules_resp.get("rules", []):
                    rules.append(
                        {
                            "short_name": rule.get("short_name"),
                            "description": rule.get("description"),
                            "kind": rule.get("kind"),
                            "priority": rule.get("priority"),
                        }
                    )
            except Exception:
                pass  # Non-critical

            info = {
                "name": sdata.get("display_name"),
                "title": sdata.get("title"),
                "description": sdata.get("public_description", ""),
                "description_html": sdata.get("description_html", ""),
                "subscribers": sdata.get("subscribers", 0),
                "active_user_count": sdata.get("active_user_count", 0),
                "created_utc": sdata.get("created_utc"),
                "nsfw": bool(sdata.get("over18")),
                "subreddit_type": sdata.get("subreddit_type"),
                "lang": sdata.get("lang"),
                "icon_img": sdata.get("icon_img"),
                "banner_img": sdata.get("banner_img"),
                "primary_color": sdata.get("primary_color"),
                "key_color": sdata.get("key_color"),
                "allow_images": bool(sdata.get("allow_images")),
                "allow_videos": bool(sdata.get("allow_videos")),
                "url": f"https://www.reddit.com/r/{subreddit}/",
                "rules": rules,
            }
            self._subreddit_cache[subreddit] = info
            return info
        except Exception as e:
            logger.debug(f"[Reddit] Could not fetch subreddit info for r/{subreddit}: {e}")
            return {}

    # ────────────────────────────────────────────────── lifecycle

    async def close(self) -> None:
        await self.api.aclose()
