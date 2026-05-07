"""
Pydantic schemas for Account operations.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AccountBase(BaseModel):
    platform: str
    username: str
    auth_token: str | None = None
    cookies_data: dict | list | None = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    is_active: bool | None = None
    is_rate_limited: bool | None = None
    rate_limited_until: datetime | None = None
    error_count: int | None = None
    last_used_at: datetime | None = None
    auth_token: str | None = None
    cookies_data: dict | list | None = None


class AccountResponse(AccountBase):
    id: int
    is_active: bool
    is_rate_limited: bool
    rate_limited_until: datetime | None
    error_count: int
    last_used_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
