from app.crawlers.youtube.visible_crawler import VisibleYouTubeCrawler
from unittest.mock import AsyncMock, patch

import pytest


def test_search_video_renderer_structures_visible_card_fields():
    renderer = {
        "videoId": "vid12345678",
        "title": {"runs": [{"text": "Visible Search Title"}]},
        "thumbnail": {
            "thumbnails": [
                {"url": "https://i.ytimg.com/vi/vid123/default.jpg"},
                {"url": "https://i.ytimg.com/vi/vid123/hqdefault.jpg"},
            ]
        },
        "lengthText": {"simpleText": "1:02:03"},
        "ownerText": {
            "runs": [
                {
                    "text": "OpenAI",
                    "navigationEndpoint": {
                        "commandMetadata": {"webCommandMetadata": {"url": "/@OpenAI"}}
                    },
                }
            ]
        },
        "ownerBadges": [
            {
                "metadataBadgeRenderer": {
                    "style": "BADGE_STYLE_TYPE_VERIFIED",
                    "tooltip": "Verified",
                }
            }
        ],
        "channelThumbnailSupportedRenderers": {
            "channelThumbnailWithLinkRenderer": {
                "thumbnail": {"thumbnails": [{"url": "https://yt3/avatar.jpg"}]}
            }
        },
        "viewCountText": {"simpleText": "1.2M views"},
        "publishedTimeText": {"simpleText": "2 days ago"},
        "detailedMetadataSnippets": [{"snippetText": {"runs": [{"text": "Visible snippet"}]}}],
        "badges": [{"metadataBadgeRenderer": {"label": "New"}}],
    }

    result = VisibleYouTubeCrawler.parse_search_video_renderer(
        renderer,
        rank=3,
        page_url="https://www.youtube.com/results?search_query=openai",
        full_yt_initial_data={"page": "raw"},
    )

    assert result.source_id == "vid12345678"
    assert result.title == "Visible Search Title"
    assert result.view_count == 1_200_000
    assert result.visible_data == {
        "card_type": "video",
        "rank": 3,
        "video_id": "vid12345678",
        "url": "https://www.youtube.com/watch?v=vid12345678",
        "title": "Visible Search Title",
        "thumbnail_urls": [
            "https://i.ytimg.com/vi/vid123/default.jpg",
            "https://i.ytimg.com/vi/vid123/hqdefault.jpg",
        ],
        "duration_text": "1:02:03",
        "duration_seconds": 3723,
        "channel_name": "OpenAI",
        "channel_handle": "@OpenAI",
        "channel_url": "https://www.youtube.com/@OpenAI",
        "channel_avatar": "https://yt3/avatar.jpg",
        "channel_verified": True,
        "view_count_text": "1.2M views",
        "view_count": 1_200_000,
        "published_text": "2 days ago",
        "description_snippet": "Visible snippet",
        "badges": ["Verified", "New"],
        "is_live": False,
        "is_upcoming": False,
        "is_short": False,
    }
    assert result.raw_sources["yt_initial_data"]["page"] == "raw"
    assert result.raw_sources["renderer"] == renderer
    assert result.capture_meta["method"] == "youtube_visible_search"


def test_watch_initial_data_structures_visible_detail_and_ytdlp_sources():
    yt_data = {
        "currentVideoEndpoint": {"watchEndpoint": {"videoId": "vid12345678"}},
        "contents": {
            "twoColumnWatchNextResults": {
                "results": {
                    "results": {
                        "contents": [
                            {
                                "videoPrimaryInfoRenderer": {
                                    "title": {"runs": [{"text": "Visible Detail Title"}]},
                                    "viewCount": {
                                        "videoViewCountRenderer": {
                                            "viewCount": {"simpleText": "42,000 views"}
                                        }
                                    },
                                    "dateText": {"simpleText": "May 4, 2026"},
                                    "videoActions": {
                                        "menuRenderer": {
                                            "topLevelButtons": [
                                                {
                                                    "segmentedLikeDislikeButtonRenderer": {
                                                        "likeButton": {
                                                            "toggleButtonRenderer": {
                                                                "defaultText": {
                                                                    "simpleText": "1.5K"
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            ]
                                        }
                                    },
                                }
                            },
                            {
                                "videoSecondaryInfoRenderer": {
                                    "owner": {
                                        "videoOwnerRenderer": {
                                            "title": {"runs": [{"text": "OpenAI"}]},
                                            "navigationEndpoint": {
                                                "commandMetadata": {
                                                    "webCommandMetadata": {"url": "/@OpenAI"}
                                                }
                                            },
                                            "thumbnail": {
                                                "thumbnails": [{"url": "https://yt3/openai.jpg"}]
                                            },
                                            "subscriberCountText": {"simpleText": "2M subscribers"},
                                        }
                                    },
                                    "description": {
                                        "runs": [
                                            {"text": "Full visible description "},
                                            {
                                                "text": "#AI",
                                                "navigationEndpoint": {
                                                    "commandMetadata": {
                                                        "webCommandMetadata": {"url": "/hashtag/ai"}
                                                    }
                                                },
                                            },
                                        ]
                                    },
                                }
                            },
                        ]
                    }
                }
            }
        },
    }
    ytdlp_info = {
        "id": "vid12345678",
        "duration": 95,
        "thumbnail": "https://i.ytimg.com/vi/vid123/maxresdefault.jpg",
        "formats": [{"format_id": "18"}],
        "chapters": [{"start_time": 0, "end_time": 10, "title": "Intro"}],
        "subtitles": {"en": [{"url": "https://subs/en.vtt"}]},
        "automatic_captions": {"zh-Hans": [{"url": "https://subs/zh.vtt"}]},
        "tags": ["ai"],
    }

    result = VisibleYouTubeCrawler.parse_watch_initial_data(
        "https://www.youtube.com/watch?v=vid12345678",
        yt_data,
        ytdlp_info,
    )

    assert result.source_id == "vid12345678"
    assert result.title == "Visible Detail Title"
    assert result.content == "Full visible description #AI"
    assert result.like_count == 1500
    assert result.view_count == 42_000
    assert result.visible_data["description_full"] == "Full visible description #AI"
    assert result.visible_data["hashtags"] == ["#AI"]
    assert result.visible_data["channel_name"] == "OpenAI"
    assert result.visible_data["channel_handle"] == "@OpenAI"
    assert result.visible_data["subscriber_count_text"] == "2M subscribers"
    assert result.visible_data["subscriber_count"] == 2_000_000
    assert result.visible_data["chapters"][0]["title"] == "Intro"
    assert result.visible_data["captions"]["manual"] == ["en"]
    assert result.visible_data["captions"]["automatic"] == ["zh-Hans"]
    assert result.visible_data["formats"][0]["format_id"] == "18"
    assert result.raw_sources["yt_initial_data"] == yt_data
    assert result.raw_sources["ytdlp"] == ytdlp_info
    assert result.capture_meta["method"] == "youtube_visible_detail"


@pytest.mark.asyncio
async def test_comments_ytdlp_fallback_respects_limit():
    crawler = VisibleYouTubeCrawler()
    raw_comments = [
        {"id": "c1", "text": "one", "parent": "root", "author": "User 1"},
        {"id": "c2", "text": "two", "parent": "root", "author": "User 2"},
    ]
    innertube = AsyncMock()
    innertube.get_comments.return_value = []
    innertube.close = AsyncMock()
    crawler.ytdlp.extract_comments_info = AsyncMock(
        return_value={"id": "vid12345678", "comments": raw_comments}
    )
    crawler.ytdlp.extract_info_with_comments = AsyncMock(
        side_effect=AssertionError("old comments method should not be used")
    )

    with (
        patch(
            "app.crawlers.youtube.visible_crawler.InnertubeClient",
            return_value=innertube,
        ),
        patch.object(
            crawler,
            "_get_comments_from_dom",
            new_callable=AsyncMock,
        ) as mock_dom,
    ):
        comments = await crawler.get_comments("vid12345678", limit=2)

    crawler.ytdlp.extract_comments_info.assert_awaited_once_with(
        "https://www.youtube.com/watch?v=vid12345678",
        max_comments=2,
    )
    mock_dom.assert_not_awaited()
    assert [comment.source_id for comment in comments] == ["c1", "c2"]
    assert comments[0].capture_meta["method"] == "youtube_ytdlp_comments"
    assert comments[0].capture_meta["limit"] == 2
