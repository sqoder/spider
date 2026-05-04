"""
Post model — 帖子 / 视频 / 推文 / Reddit 帖子.
All platform content goes into this single table.
post_type: video | image | text | link | album | short | reel | tweet | reddit_post
"""

from datetime import datetime

import enum
from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, Index, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class PostType(str, enum.Enum):
    VIDEO = "video"
    IMAGE = "image"
    TEXT = "text"
    LINK = "link"
    ALBUM = "album"
    SHORT = "short"
    REEL = "reel"
    TWEET = "tweet"
    REDDIT_POST = "reddit_post"
    CAROUSEL = "carousel"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("authors.id", ondelete="SET NULL"), nullable=True
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_type: Mapped[PostType | None] = mapped_column(String(50), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )

    # Metrics
    like_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    comment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    share_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Raw API response (always preserve for debugging)
    raw_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    visible_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    raw_sources: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    capture_meta: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    author = relationship("Author", back_populates="posts", lazy="selectin")
    comments = relationship(
        "Comment", back_populates="post", lazy="selectin", cascade="all, delete-orphan"
    )
    media_assets = relationship(
        "MediaAsset",
        back_populates="post",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("platform", "source_id", name="uq_posts_platform_source_id"),
        Index("idx_posts_platform_published_at", "platform", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, platform={self.platform}, source_id={self.source_id})>"
