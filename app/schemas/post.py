"""
Pydantic schemas for Post.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PostBase(BaseModel):
    platform: str
    source_id: str
    url: str | None = None
    title: str | None = None
    content: str | None = None
    post_type: str | None = None
    published_at: datetime | None = None
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    view_count: int = 0
    raw_data: dict | None = None


class PostCreate(PostBase):
    """Used when creating / upserting a post from crawler output."""

    author_id: int | None = None


class PostUpdate(BaseModel):
    """Partial update."""

    title: str | None = None
    content: str | None = None
    post_type: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    view_count: int | None = None
    raw_data: dict | None = None


class PostOut(PostBase):
    """Response model returned by API."""

    id: int
    author_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostListOut(BaseModel):
    """Paginated list response."""

    items: list[PostOut]
    total: int
    page: int = 1
    page_size: int = 20
