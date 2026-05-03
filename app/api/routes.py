"""
API route definitions for GlobalMediaCrawler.
Provides endpoints for task management, content retrieval, and direct crawling.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.base import CrawlResult
from app.crawlers.factory import CrawlerFactory
from app.models.database import get_db
from app.models.schemas import (
    APIResponse,
    CreateTaskRequest,
    PostListResponse,
    PostResponse,
    SearchRequest,
    TaskResponse,
    UrlCrawlRequest,
    UserCrawlRequest,
)
from app.models.task import TaskStatus, TaskType
from app.storage.postgres import PostgresStorage
from app.storage.redis import redis_storage

router = APIRouter(prefix="/api", tags=["crawler"])


# ============================================================
# Health Check
# ============================================================

@router.get("/health", response_model=APIResponse)
async def health_check():
    """Health check endpoint."""
    platforms = CrawlerFactory.get_supported_platforms()
    return APIResponse(
        success=True,
        message="GlobalMediaCrawler is running",
        data={
            "version": "0.1.0",
            "supported_platforms": platforms,
            "redis_connected": redis_storage.is_connected,
        },
    )


# ============================================================
# Task Management
# ============================================================

@router.post("/tasks", response_model=APIResponse)
async def create_task(
    request: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new crawl task (async, queued via Celery)."""
    storage = PostgresStorage(db)

    # Validate platform is supported
    if not CrawlerFactory.is_supported(request.platform.value):
        raise HTTPException(
            status_code=400,
            detail=f"Platform '{request.platform.value}' is not supported",
        )

    # Create task record
    task = await storage.create_task(
        platform=request.platform.value,
        task_type=request.type.value,
        status=TaskStatus.PENDING,
        keyword=request.keyword,
        username=request.username,
        url=request.url,
        limit=request.limit,
        params=request.params,
    )
    await db.commit()

    # Dispatch to Celery (if available)
    celery_task_id = None
    try:
        from app.workers.crawler_worker import execute_crawl_task
        celery_result = execute_crawl_task.delay(task.id)
        celery_task_id = celery_result.id
        task.celery_task_id = celery_task_id
        await db.commit()
    except Exception as e:
        logger.warning(f"Celery dispatch failed (will run inline): {e}")

    return APIResponse(
        success=True,
        message="Task created successfully",
        data=task.to_dict(),
    )


@router.get("/tasks/{task_id}", response_model=APIResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get task status and details."""
    storage = PostgresStorage(db)
    task = await storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Try to get real-time progress from Redis
    progress = await redis_storage.get_task_progress(task_id)
    data = task.to_dict()
    if progress:
        data["progress"] = progress

    return APIResponse(data=data)


@router.get("/tasks", response_model=APIResponse)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List crawl tasks with optional filters."""
    storage = PostgresStorage(db)
    tasks, total = await storage.list_tasks(
        status=status, platform=platform, page=page, page_size=page_size
    )

    return APIResponse(
        data={
            "items": [t.to_dict() for t in tasks],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ============================================================
# Content (Posts) Retrieval
# ============================================================

@router.get("/posts", response_model=APIResponse)
async def list_posts(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List crawled posts with optional platform filter."""
    storage = PostgresStorage(db)
    posts, total = await storage.list_posts(
        platform=platform, page=page, page_size=page_size
    )

    return APIResponse(
        data={
            "items": [p.to_unified_dict() for p in posts],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/posts/{post_id}", response_model=APIResponse)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single post by database ID."""
    storage = PostgresStorage(db)
    post = await storage.get_post(post_id)

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return APIResponse(data=post.to_unified_dict())


# ============================================================
# Direct Crawl (Synchronous)
# ============================================================

@router.post("/crawl/search", response_model=APIResponse)
async def crawl_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Directly search a platform and return results.
    Results are also saved to the database.
    """
    platform = request.platform.value

    if not CrawlerFactory.is_supported(platform):
        raise HTTPException(
            status_code=400,
            detail=f"Platform '{platform}' is not supported",
        )

    # Check cache first
    cache_key = f"search:{platform}:{request.keyword}:{request.limit}"
    cached = await redis_storage.cache_json_get(cache_key)
    if cached:
        logger.info(f"Cache hit for search: {cache_key}")
        return APIResponse(
            data=cached,
            message="Results from cache",
        )

    try:
        crawler = CrawlerFactory.create(platform)
        results = await crawler.search(request.keyword, limit=request.limit)

        # Save to database
        storage = PostgresStorage(db)
        await storage.save_crawl_results(results)

        # Convert to response format
        response_data = {
            "platform": platform,
            "keyword": request.keyword,
            "count": len(results),
            "items": [r.to_dict() for r in results],
        }

        # Cache results
        await redis_storage.cache_json_set(cache_key, response_data, ttl=1800)

        await crawler.close()
        return APIResponse(data=response_data)

    except Exception as e:
        logger.error(f"Crawl search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawl/user", response_model=APIResponse)
async def crawl_user(
    request: UserCrawlRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Directly crawl a user's posts and return results.
    Results are also saved to the database.
    """
    platform = request.platform.value

    if not CrawlerFactory.is_supported(platform):
        raise HTTPException(
            status_code=400,
            detail=f"Platform '{platform}' is not supported",
        )

    try:
        crawler = CrawlerFactory.create(platform)
        results = await crawler.get_user_posts(request.username, limit=request.limit)

        # Save to database
        storage = PostgresStorage(db)
        await storage.save_crawl_results(results)

        response_data = {
            "platform": platform,
            "username": request.username,
            "count": len(results),
            "items": [r.to_dict() for r in results],
        }

        await crawler.close()
        return APIResponse(data=response_data)

    except Exception as e:
        logger.error(f"Crawl user failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawl/url", response_model=APIResponse)
async def crawl_url(
    request: UrlCrawlRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Parse a single URL and return the content detail.
    Results are also saved to the database.
    """
    platform = request.platform.value

    if not CrawlerFactory.is_supported(platform):
        raise HTTPException(
            status_code=400,
            detail=f"Platform '{platform}' is not supported",
        )

    try:
        crawler = CrawlerFactory.create(platform)
        result = await crawler.get_post_detail(request.url)

        # Save to database
        storage = PostgresStorage(db)
        await storage.upsert_post(result)
        await db.commit()

        await crawler.close()
        return APIResponse(data=result.to_dict())

    except Exception as e:
        logger.error(f"Crawl URL failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Storage Stats
# ============================================================

@router.get("/stats", response_model=APIResponse)
async def get_stats():
    """Get system statistics."""
    from app.storage.media_storage import media_storage

    return APIResponse(
        data={
            "platforms": CrawlerFactory.get_supported_platforms(),
            "media_storage": media_storage.get_stats(),
            "redis_connected": redis_storage.is_connected,
        }
    )
