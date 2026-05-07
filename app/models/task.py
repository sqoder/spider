"""
CrawlTask model — 抓取任务.
Tracks async crawl jobs with status, counts, and error info.
task_type: search | user_posts | post_detail | comments | url_parse
status: pending | running | success | failed | partial_success
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CrawlTask(Base):
    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Task input params
    keyword: Mapped[str | None] = mapped_column(String(500), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        server_default="pending",
        index=True,
        nullable=False,
    )
    limit_count: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    success_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Celery integration
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Extra params (JSON)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlTask(id={self.id}, platform={self.platform}, "
            f"type={self.task_type}, status={self.status})>"
        )
