"""
MediaAsset repository — CRUD operations for the media_assets table.
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import MediaAsset
from app.schemas.media import MediaCreate


class MediaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: MediaCreate) -> MediaAsset:
        asset = MediaAsset(**data.model_dump())
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def bulk_create(self, items: list[MediaCreate]) -> list[MediaAsset]:
        results = []
        for data in items:
            asset = MediaAsset(**data.model_dump())
            self.db.add(asset)
            results.append(asset)
        await self.db.commit()
        for asset in results:
            await self.db.refresh(asset)
        return results

    async def get_by_id(self, asset_id: int) -> MediaAsset | None:
        return await self.db.get(MediaAsset, asset_id)

    async def list_by_post(
        self,
        post_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MediaAsset], int]:
        count_query = select(func.count(MediaAsset.id)).where(MediaAsset.post_id == post_id)
        total = (await self.db.execute(count_query)).scalar() or 0

        query = (
            select(MediaAsset)
            .where(MediaAsset.post_id == post_id)
            .order_by(MediaAsset.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def update_local_path(self, asset_id: int, local_path: str) -> MediaAsset | None:
        asset = await self.db.get(MediaAsset, asset_id)
        if not asset:
            return None
        asset.local_path = local_path
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def delete(self, asset_id: int) -> bool:
        asset = await self.db.get(MediaAsset, asset_id)
        if not asset:
            return False
        await self.db.delete(asset)
        await self.db.commit()
        return True
