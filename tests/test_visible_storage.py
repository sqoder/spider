import pytest
from sqlalchemy import select

from app.models.comment import Comment
from app.models.post import Post
from app.storage.db_store_impl import DbStoreImplement


@pytest.mark.asyncio
async def test_db_store_persists_visible_contract_fields():
    store = DbStoreImplement("youtube", "detail")

    try:
        await store.store_content(
            [
                {
                    "platform": "youtube",
                    "source_id": "vid12345678",
                    "url": "https://www.youtube.com/watch?v=vid12345678",
                    "title": "Visible Detail Title",
                    "content": "Visible description",
                    "content_type": "video",
                    "metrics": {"view_count": 42000, "like_count": 1500},
                    "visible_data": {"title": "Visible Detail Title"},
                    "raw_sources": {"yt_initial_data": {"ok": True}},
                    "capture_meta": {"method": "youtube_visible_detail"},
                }
            ]
        )
        await store.store_comment(
            "vid12345678",
            [
                {
                    "source_id": "comment1",
                    "content": "Visible comment",
                    "author_name": "User1",
                    "visible_data": {"content_text": "Visible comment"},
                    "raw_sources": {"innertube": {"commentId": "comment1"}},
                    "capture_meta": {"method": "innertube_comments"},
                }
            ],
        )

        session = await store._get_session()
        post = (
            await session.execute(
                select(Post).where(Post.platform == "youtube", Post.source_id == "vid12345678")
            )
        ).scalar_one()
        comment = (
            await session.execute(
                select(Comment).where(
                    Comment.platform == "youtube", Comment.source_id == "comment1"
                )
            )
        ).scalar_one()

        assert post.visible_data["title"] == "Visible Detail Title"
        assert post.raw_sources["yt_initial_data"]["ok"] is True
        assert post.capture_meta["method"] == "youtube_visible_detail"
        assert comment.visible_data["content_text"] == "Visible comment"
        assert comment.raw_sources["innertube"]["commentId"] == "comment1"
    finally:
        await store.close()
