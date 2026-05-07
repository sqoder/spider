"""
Database model for the Account Pool (used for massive non-API crawling).
"""

from datetime import datetime, UTC

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class Account(Base):
    """Stores platform-specific accounts, tokens, and cookies for anti-bot bypass."""

    __tablename__ = "account_pool"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Store auth tokens directly (like Twitter auth_token) or a full cookie dump
    auth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    cookies_data: Mapped[dict | list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    
    # Health and rotation tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_rate_limited: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    error_count: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
