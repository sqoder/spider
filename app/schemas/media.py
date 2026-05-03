"""
Pydantic schemas for MediaAsset.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaBase(BaseModel):
    platform: str
    post_id: int
    media_type: str  # image | video | audio | thumbnail | subtitle
    source_url: str | None = None
    local_path: str | None = None
    thumbnail_url: str | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    raw_data: dict | None = None


class MediaCreate(MediaBase):
    pass


class MediaOut(MediaBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
