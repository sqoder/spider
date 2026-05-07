import asyncio
import json
import os
import re

from loguru import logger
from scrapling import Fetcher
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.proxy_manager import proxy_manager
from app.crawlers.base import CommentResult

# Module-level cookie cache: {filepath: (mtime, cookies_dict)}
_innertube_cookie_cache: dict[str, tuple[float, dict]] = {}


class InnertubeClient:
    def __init__(self):
        self.settings = get_settings()

        # Use project proxy if enabled
        self.proxy = None
        if proxy_manager.enabled:
            self.proxy = proxy_manager.get_proxy()
            logger.info(f"Innertube using proxy: {self.proxy}")

        # Load cookies with caching (shared across instances)
        self.cookies = None
        if self.settings.youtube_cookies_file and os.path.exists(
            self.settings.youtube_cookies_file
        ):
            self.cookies = self._parse_cookies_for_scrapling(self.settings.youtube_cookies_file)

        # Initialize Scrapling Fetcher
        self.fetcher = Fetcher(
            proxy=self.proxy,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            timeout=30000,
        )
        self.api_key = None
        self.context = None

    def _parse_cookies_for_scrapling(self, filepath: str) -> dict:
        """Parse Netscape format cookies for Scrapling. Results are cached by mtime."""
        try:
            current_mtime = os.path.getmtime(filepath)
        except OSError:
            return {}
        cached_mtime, cached = _innertube_cookie_cache.get(filepath, (0, {}))
        if cached_mtime == current_mtime:
            return cached

        cookies = {}
        try:
            with open(filepath) as f:
                for line in f:
                    if not line.strip() or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        cookies[parts[5].strip()] = parts[6].strip()
            _innertube_cookie_cache[filepath] = (current_mtime, cookies)
        except Exception as e:
            logger.error(f"Failed to parse cookies for Scrapling: {e}")
        return cookies

    def _extract_json(self, html: str, start_pattern: str) -> dict:
        match = re.search(start_pattern, html)
        if not match:
            return None

        start_index = match.end() - 1
        obj_str = ""
        brace_count = 0
        in_string = False
        prev_char = ""
        for i in range(start_index, len(html)):
            char = html[i]
            obj_str += char

            if char == '"' and prev_char != "\\":
                in_string = not in_string

            if not in_string:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        break
            prev_char = char

        try:
            return json.loads(obj_str)
        except Exception as e:
            logger.error(f"Failed to parse extracted JSON: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get_initial_data(self, video_id: str):
        url = f"https://www.youtube.com/watch?v={video_id}"

        def _do_fetch():
            return self.fetcher.get(url, cookies=self.cookies)

        response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)
        html = response.text

        # Extract API Key - Broaden regex
        api_key_match = re.search(r'["\']INNERTUBE_API_KEY["\']\s*:\s*["\']([^"\']+)["\']', html)
        if not api_key_match:
            # More targeted fallback: look for common Innertube key patterns
            api_key_match = re.search(r'["\']key["\']\s*:\s*["\']([A-Za-z0-9_-]{30,})["\']', html)

        if not api_key_match:
            logger.error(f"Failed to find API key in HTML for {video_id}")
            raise Exception("Could not find INNERTUBE_API_KEY")

        self.api_key = api_key_match.group(1)

        # Extract Context - More robust extraction
        self.context = self._extract_json(html, r'["\']INNERTUBE_CONTEXT["\']\s*:\s*\{')
        if not self.context:
            self.context = self._extract_json(
                html, r'ytcfg\.set\(\{.*?"INNERTUBE_CONTEXT"\s*:\s*\{'
            )

        if not self.context:
            logger.error(f"Failed to find context in HTML for {video_id}")
            raise Exception("Could not find INNERTUBE_CONTEXT")

        # Extract initial data for continuation
        yt_data = self._extract_json(html, r"var ytInitialData = \{")
        if not yt_data:
            yt_data = self._extract_json(html, r'window\["ytInitialData"\]\s*=\s*\{')

        if not yt_data:
            logger.error(f"Failed to find ytInitialData in HTML for {video_id}")
            raise Exception("Could not find ytInitialData")

        return yt_data

    async def get_comments(self, video_id: str, limit: int = 100) -> list[CommentResult]:
        try:
            yt_data = await self._get_initial_data(video_id)

            # Find the continuation token
            continuation_token = self._extract_initial_continuation(yt_data)

            if not continuation_token:
                logger.warning(f"No comments found or comments disabled for {video_id}")
                return []

            results = []
            pending_reply_tokens = []  # (parent_id, token) tuples

            while continuation_token and len(results) < limit:
                data = await self._fetch_next(continuation_token)
                new_comments, continuation_token, reply_tokens = self._parse_comment_data(
                    data, entity_lookup_override=None
                )
                results.extend(new_comments)
                pending_reply_tokens.extend(reply_tokens)

                if not new_comments:
                    break

            # Fetch reply continuations for threads with more replies
            logger.info(
                f"[Innertube] Found {len(pending_reply_tokens)} threads with reply continuations"
            )
            for parent_id, token in pending_reply_tokens:
                if len(results) >= limit:
                    break
                logger.debug(f"[Innertube] Fetching replies for thread {parent_id}")
                while token and len(results) < limit:
                    data = await self._fetch_next(token)
                    if not data:
                        logger.warning(
                            f"[Innertube] Reply continuation returned empty data for thread {parent_id}"
                        )
                        break
                    new_replies, token = self._parse_reply_continuation_data(data, parent_id)
                    logger.debug(
                        f"[Innertube] Fetched {len(new_replies)} more replies for thread {parent_id}, has_more={token is not None}"
                    )
                    results.extend(new_replies)
                    if not new_replies:
                        break

            return results[:limit]
        except Exception as e:
            import traceback

            logger.error(f"Innertube error for {video_id}: {str(e)}")
            logger.debug(traceback.format_exc())
            return []

    def _extract_initial_continuation(self, yt_data):
        """Recursively find the first comment continuation token."""

        def find_token(obj):
            if isinstance(obj, dict):
                # Look for the specific continuation item for comments
                if "continuationItemRenderer" in obj:
                    endpoint = obj["continuationItemRenderer"].get("continuationEndpoint", {})
                    command = endpoint.get("continuationCommand", {})
                    if "token" in command:
                        # Ensure it is a comment continuation (usually has specific patterns)
                        return command["token"]

                # Check for itemSectionRenderer with comments
                if obj.get("sectionIdentifier") == "comment-item-section":
                    # Deep search inside this specific section
                    return find_token(obj.get("contents"))

                for v in obj.values():
                    res = find_token(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_token(item)
                    if res:
                        return res
            return None

        # Start search from contents
        token = find_token(yt_data.get("contents", {}))
        if not token:
            # Fallback: check engagement panels (sometimes comments live there in mobile/new UI)
            token = find_token(yt_data.get("engagementPanels", []))

        return token

    async def _fetch_next(self, token: str):
        url = f"https://www.youtube.com/youtubei/v1/next?key={self.api_key}"
        payload = {"context": self.context, "continuation": token}

        # Add mandatory headers for Innertube
        headers = {
            "Content-Type": "application/json",
            "X-Youtube-Client-Name": str(self.context.get("client", {}).get("clientName", "1")),
            "X-Youtube-Client-Version": self.context.get("client", {}).get(
                "clientVersion", "2.20240210.01.00"
            ),
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        }

        def _do_fetch():
            return self.fetcher.post(url, json=payload, headers=headers, cookies=self.cookies)

        response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        if response.status_code != 200:
            logger.error(
                f"Innertube API failed with status {response.status_code}: {response.text[:200]}"
            )
            return {}

        try:
            return response.json()
        except Exception:
            logger.error(
                f"Failed to parse Innertube JSON. Status: {response.status_code}, Body: {response.text[:200]}"
            )
            return {}

    @staticmethod
    def _build_entity_lookup(data: dict) -> dict:
        """Build key -> entity mapping from frameworkUpdates mutations."""
        lookup = {}
        framework = data.get("frameworkUpdates", {})
        mutations = framework.get("entityBatchUpdate", {}).get("mutations", [])
        for mutation in mutations:
            payload = mutation.get("payload", {})
            for _entity_key, entity_val in payload.items():
                if "key" in entity_val:
                    lookup[entity_val["key"]] = entity_val
        return lookup

    def _parse_comment_data(self, data, entity_lookup_override=None):
        comments = []
        new_token = None
        reply_tokens = []  # (parent_id, continuation_token)
        position = 1

        endpoints = data.get("onResponseReceivedEndpoints", [])
        if not endpoints:
            framework = data.get("frameworkUpdates", {})
            if framework:
                endpoints = framework.get("entityBatchUpdate", {}).get("mutations", [])
            if not endpoints:
                logger.warning(f"No endpoints in comment response. Keys: {list(data.keys())}")
                return [], None, []

        # Build entity lookup for the new YouTube API format
        entity_lookup = entity_lookup_override or self._build_entity_lookup(data)

        for endpoint in endpoints:
            command = endpoint.get("reloadContinuationItemsCommand") or endpoint.get(
                "appendContinuationItemsAction"
            )
            if not command:
                if "continuationItems" in endpoint:
                    command = endpoint
                else:
                    continue

            items = command.get("continuationItems", [])
            if not items:
                logger.debug(f"No continuationItems in command. Keys: {list(command.keys())}")
                continue

            for item in items:
                if "commentThreadRenderer" in item:
                    thread = item["commentThreadRenderer"]

                    # Check new YouTube entity-based format
                    if "commentViewModel" in thread:
                        cvm = thread["commentViewModel"].get("commentViewModel", {})
                        entity = entity_lookup.get(cvm.get("commentKey"), {})
                        if entity:
                            comment_result = self._parse_comment_entity(
                                entity,
                                raw_source=item,
                                thread_position=position,
                            )
                            if comment_result:
                                comments.append(comment_result)
                                position += 1

                                replies = (
                                    thread.get("replies", {})
                                    .get("commentRepliesRenderer", {})
                                    .get("contents", [])
                                )
                                parent_id = comment_result.source_id
                                for reply_item in replies:
                                    if "commentViewModel" in reply_item:
                                        r_cvm = reply_item["commentViewModel"].get(
                                            "commentViewModel", {}
                                        )
                                        r_entity = entity_lookup.get(r_cvm.get("commentKey"), {})
                                        if r_entity:
                                            reply_result = self._parse_comment_entity(
                                                r_entity,
                                                raw_source=reply_item,
                                                thread_position=position,
                                                parent_comment_id=parent_id,
                                            )
                                            if reply_result:
                                                comments.append(reply_result)
                                                position += 1
                                    elif "commentRenderer" in reply_item:
                                        comments.append(
                                            self._parse_comment_renderer(
                                                reply_item["commentRenderer"],
                                                raw_source=reply_item,
                                                thread_position=position,
                                                parent_comment_id=parent_id,
                                            )
                                        )
                                        position += 1
                                    elif "continuationItemRenderer" in reply_item:
                                        cont = reply_item["continuationItemRenderer"]
                                        ep = cont.get("continuationEndpoint", {})
                                        cmd = ep.get("continuationCommand", {})
                                        if "token" in cmd:
                                            reply_tokens.append((parent_id, cmd["token"]))
                                            logger.debug(
                                                f"[Innertube] Reply continuation found (entity) for thread {parent_id}: token={cmd['token'][:40]}..."
                                            )
                        else:
                            # Fallback: try old format
                            comment_renderer = thread.get("comment", {}).get("commentRenderer", {})
                            if comment_renderer:
                                comment_result = self._parse_comment_renderer(
                                    comment_renderer,
                                    raw_source=item,
                                    thread_position=position,
                                )
                                comments.append(comment_result)
                                position += 1
                                parent_id = comment_renderer.get("commentId")
                                replies = (
                                    thread.get("replies", {})
                                    .get("commentRepliesRenderer", {})
                                    .get("contents", [])
                                )
                                for reply_item in replies:
                                    if "commentRenderer" in reply_item:
                                        comments.append(
                                            self._parse_comment_renderer(
                                                reply_item["commentRenderer"],
                                                raw_source=reply_item,
                                                thread_position=position,
                                                parent_comment_id=parent_id,
                                            )
                                        )
                                        position += 1
                                    elif "continuationItemRenderer" in reply_item:
                                        cont = reply_item["continuationItemRenderer"]
                                        ep = cont.get("continuationEndpoint", {})
                                        cmd = ep.get("continuationCommand", {})
                                        if "token" in cmd:
                                            reply_tokens.append((parent_id, cmd["token"]))
                                            logger.debug(
                                                f"[Innertube] Reply continuation found (old entity fallback) for thread {parent_id}"
                                            )
                    else:
                        # Old YouTube API format: comment -> commentRenderer
                        comment_renderer = thread.get("comment", {}).get("commentRenderer", {})
                        if not comment_renderer:
                            continue
                        comments.append(
                            self._parse_comment_renderer(
                                comment_renderer,
                                raw_source=item,
                                thread_position=position,
                            )
                        )
                        position += 1

                        replies = (
                            thread.get("replies", {})
                            .get("commentRepliesRenderer", {})
                            .get("contents", [])
                        )
                        parent_id = comment_renderer.get("commentId")
                        for reply_item in replies:
                            if "commentRenderer" in reply_item:
                                reply_renderer = reply_item.get("commentRenderer")
                                if not reply_renderer:
                                    continue
                                comments.append(
                                    self._parse_comment_renderer(
                                        reply_renderer,
                                        raw_source=reply_item,
                                        thread_position=position,
                                        parent_comment_id=parent_id,
                                    )
                                )
                                position += 1
                            elif "continuationItemRenderer" in reply_item:
                                cont = reply_item["continuationItemRenderer"]
                                ep = cont.get("continuationEndpoint", {})
                                cmd = ep.get("continuationCommand", {})
                                if "token" in cmd:
                                    reply_tokens.append((parent_id, cmd["token"]))
                                    logger.debug(
                                        f"[Innertube] Reply continuation found (old renderer) for thread {parent_id}"
                                    )

                elif "continuationItemRenderer" in item:
                    continuation = item["continuationItemRenderer"]
                    endpoint = continuation.get("continuationEndpoint", {})
                    command = endpoint.get("continuationCommand", {})
                    if "token" in command:
                        new_token = command["token"]

        return comments, new_token, reply_tokens

    def _parse_reply_continuation_data(self, data, parent_id: str):
        """Parse reply continuation response (more replies for a thread)."""
        replies = []
        new_token = None
        position = 1
        entity_lookup = self._build_entity_lookup(data)

        endpoints = data.get("onResponseReceivedEndpoints", [])
        for endpoint in endpoints:
            action = endpoint.get("appendContinuationItemsAction")
            if not action:
                action = endpoint.get("reloadContinuationItemsCommand")
            if not action:
                if "continuationItems" in endpoint:
                    action = endpoint
                else:
                    continue
            items = action.get("continuationItems", [])
            for item in items:
                if "commentRenderer" in item:
                    replies.append(
                        self._parse_comment_renderer(
                            item["commentRenderer"],
                            raw_source=item,
                            thread_position=position,
                            parent_comment_id=parent_id,
                        )
                    )
                    position += 1
                elif "commentViewModel" in item:
                    cvm = item["commentViewModel"].get("commentViewModel", {})
                    entity = entity_lookup.get(cvm.get("commentKey"), {})
                    if entity:
                        reply = self._parse_comment_entity(
                            entity,
                            raw_source=item,
                            thread_position=position,
                            parent_comment_id=parent_id,
                        )
                        if reply:
                            replies.append(reply)
                            position += 1
                elif "continuationItemRenderer" in item:
                    cont = item["continuationItemRenderer"]
                    ep = cont.get("continuationEndpoint", {})
                    cmd = ep.get("continuationCommand", {})
                    if "token" in cmd:
                        new_token = cmd["token"]

        return replies, new_token

    def _parse_comment_entity(
        self,
        entity: dict,
        raw_source: dict,
        thread_position: int,
        parent_comment_id: str | None = None,
    ) -> CommentResult | None:
        """Parse comment data from the new YouTube entity-based format."""
        props = entity.get("properties", {})
        author = entity.get("author", {})
        toolbar = entity.get("toolbar", {})
        avatar = entity.get("avatar", {})

        comment_id = props.get("commentId")
        if not comment_id:
            return None

        content = ""
        content_data = props.get("content", {})
        if isinstance(content_data, dict):
            content = content_data.get("content", "")
        elif isinstance(content_data, str):
            content = content_data

        author_name = author.get("displayName", "")
        author_handle = author.get("channelId", "")
        author_channel_cmd = author.get("channelCommand", {})
        innertube_cmd = author_channel_cmd.get("innertubeCommand", {})
        cmd_metadata = innertube_cmd.get("commandMetadata", {})
        web_metadata = cmd_metadata.get("webCommandMetadata", {})
        author_url = web_metadata.get("url", "")
        if author_url and not author_url.startswith("http"):
            author_url = f"https://www.youtube.com{author_url}"

        avatar_images = avatar.get("image", {}).get("sources", [])
        author_avatar = avatar_images[-1].get("url") if avatar_images else None
        author_avatar = author_avatar or author.get("avatarThumbnailUrl")

        is_author_owner = author.get("isCreator", False)
        published_text = props.get("publishedTime", "")

        like_count_text = toolbar.get("likeCountNotliked", "0")
        like_count = self._parse_count(like_count_text)
        reply_count_text = toolbar.get("replyCount", "0")
        reply_count = self._parse_count(reply_count_text)

        # Check isVerified or author badges
        author_badges = []
        if author.get("isVerified"):
            author_badges.append("Verified")
        if is_author_owner:
            author_badges.append("Creator")

        visible_data = {
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "thread_position": thread_position,
            "is_reply": parent_comment_id is not None,
            "author_name": author_name,
            "author_handle": author_handle,
            "author_url": author_url,
            "author_avatar": author_avatar,
            "author_badges": author_badges,
            "content_text": content,
            "published_text": published_text,
            "like_count_text": like_count_text,
            "like_count": like_count,
            "reply_count_text": reply_count_text,
            "reply_count": reply_count,
        }

        return CommentResult(
            platform="youtube",
            source_id=comment_id,
            content=content,
            author_name=author_name,
            author_username=author_handle,
            author_id=author.get("channelId"),
            like_count=like_count,
            reply_count=reply_count,
            parent_comment_id=parent_comment_id,
            published_at=None,
            raw=raw_source,
            visible_data=visible_data,
            raw_sources={"innertube_entity": entity},
            capture_meta={"method": "innertube_comments_entity"},
        )

    def _parse_comment_renderer(
        self,
        renderer: dict,
        raw_source: dict,
        thread_position: int,
        parent_comment_id: str | None = None,
    ) -> CommentResult:
        comment_id = renderer.get("commentId") or f"innertube_{thread_position}"
        author_name = self._text(renderer.get("authorText"))
        content = self._text(renderer.get("contentText"))
        published_text = self._text(renderer.get("publishedTimeText"))
        like_count_text = self._text(renderer.get("voteCount"))
        like_count = self._parse_count(like_count_text)
        author_endpoint = renderer.get("authorEndpoint", {}).get("browseEndpoint", {})
        author_handle = author_endpoint.get("canonicalBaseUrl", "").rstrip("/").split("/")[-1]
        author_url = f"https://www.youtube.com/{author_handle}" if author_handle else None
        thumbnails = renderer.get("authorThumbnail", {}).get("thumbnails", [])
        author_avatar = thumbnails[-1].get("url") if thumbnails else None
        author_badges = self._badges(renderer.get("authorCommentBadge"))
        is_pinned = "pinnedCommentBadge" in renderer
        is_creator_hearted = "creatorHeart" in renderer
        is_author_owner = bool(renderer.get("authorIsChannelOwner"))

        visible_data = {
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "thread_position": thread_position,
            "is_reply": parent_comment_id is not None,
            "author_name": author_name,
            "author_handle": author_handle,
            "author_url": author_url,
            "author_avatar": author_avatar,
            "author_badges": author_badges,
            "content_text": content,
            "published_text": published_text,
            "like_count_text": like_count_text,
            "like_count": like_count,
            "reply_count_text": self._text(renderer.get("replyCount")),
            "reply_count": self._parse_count(self._text(renderer.get("replyCount"))),
            "is_pinned": is_pinned,
            "is_creator_hearted": is_creator_hearted,
            "is_author_owner": is_author_owner,
        }

        return CommentResult(
            platform="youtube",
            source_id=comment_id,
            content=content,
            author_name=author_name,
            author_username=author_handle,
            author_id=author_endpoint.get("browseId"),
            like_count=like_count,
            parent_comment_id=parent_comment_id,
            published_at=None,
            raw=raw_source,
            visible_data=visible_data,
            raw_sources={"innertube": renderer},
            capture_meta={"method": "innertube_comments"},
        )

    @staticmethod
    def _text(value) -> str:
        if not value:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            if isinstance(value.get("simpleText"), str):
                return value["simpleText"]
            runs = value.get("runs")
            if isinstance(runs, list):
                return "".join(run.get("text", "") for run in runs)
        return ""

    @staticmethod
    def _badges(value) -> list[str]:
        if not value:
            return []
        if isinstance(value, dict):
            value = [value]
        badges = []
        for item in value:
            renderer = item.get("metadataBadgeRenderer", item)
            label = (
                renderer.get("label")
                or renderer.get("tooltip")
                or renderer.get("accessibilityData", {}).get("label")
            )
            if label:
                badges.append(label)
        return badges

    @staticmethod
    def _parse_count(text: str) -> int:
        if not text:
            return 0
        normalized = text.lower().replace(",", "")
        match = re.search(r"([\d.]+)\s*([kmb]?)", normalized)
        if not match:
            return 0
        value = float(match.group(1))
        suffix = match.group(2)
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1)
        return int(value * multiplier)

    async def close(self):
        # Scrapling Fetcher doesn't need explicit aclose usually
        pass
