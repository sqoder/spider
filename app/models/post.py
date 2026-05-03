"""
Post model — 帖子 / 视频 / 推文 / Reddit 帖子.
All platform content goes into this single table.
post_type: video | image | text | link | album | short | reel | tweet | reddit_post
"""

from datetime import datetime

from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


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
    post_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Metrics
    like_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    comment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    share_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Raw API response (always preserve for debugging)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
    )

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, platform={self.platform}, source_id={self.source_id})>"
