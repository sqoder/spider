"""
Pydantic schemas for Author.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthorBase(BaseModel):
    platform: str
    source_id: str
    username: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    raw_data: dict | None = None


class AuthorCreate(AuthorBase):
    """Used when creating / upserting an author from crawler output."""

    pass


class AuthorUpdate(BaseModel):
    """Partial update — only set fields are written."""

    username: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    raw_data: dict | None = None


class AuthorOut(AuthorBase):
    """Response model returned by API."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
