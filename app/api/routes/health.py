"""
Health check endpoint.
"""

from fastapi import APIRouter

from app.crawlers.factory import CrawlerFactory
from app.storage.redis import redis_storage

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    return {
        "success": True,
        "message": "GlobalMediaCrawler is running",
        "data": {
            "version": "0.2.0",
            "supported_platforms": CrawlerFactory.get_supported_platforms(),
            "redis_connected": redis_storage.is_connected,
        },
    }
