"""
Pydantic schemas for Comment.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CommentBase(BaseModel):
    platform: str
    source_id: str
    post_id: int
    author_name: str | None = None
    author_source_id: str | None = None
    content: str | None = None
    like_count: int = 0
    reply_count: int = 0
    parent_comment_id: str | None = None
    published_at: datetime | None = None
    raw_data: dict | None = None
    visible_data: dict | None = None
    raw_sources: dict | None = None
    capture_meta: dict | None = None


class CommentCreate(CommentBase):
    pass


class CommentOut(CommentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
