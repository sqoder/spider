"""
GlobalMediaCrawler - FastAPI Application Entry Point.
Phase 2: Unified data model + Repository pattern.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import (CrawlerBaseError, PlatformNotSupportedError,
                                 QuotaExhaustedError, RateLimitExceededError)
from app.core.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # ---- Startup ----
    setup_logger()
    logger.info("🚀 Starting GlobalMediaCrawler...")

    settings = get_settings()

    # Initialize database (create tables if not using Alembic)
    from app.db.session import init_db

    await init_db()
    logger.info("✅ Database initialized")

    # Initialize Redis (best-effort, app works without it)
    try:
        from app.storage.redis import redis_storage

        await redis_storage.connect()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.warning(f"⚠️ Redis unavailable: {e}")

    # Setup rate limiter
    try:
        from app.core.rate_limiter import setup_rate_limiter

        setup_rate_limiter()
        logger.info("✅ Rate limiter configured")
    except Exception:
        pass

    # Register all crawlers
    try:
        from app.crawlers.factory import register_all_crawlers

        register_all_crawlers()
        logger.info("✅ Crawlers registered")
    except Exception:
        pass

    logger.info(f"🌐 GlobalMediaCrawler ready | env={settings.app_env}")

    yield

    # ---- Shutdown ----
    logger.info("Shutting down GlobalMediaCrawler...")
    try:
        from app.storage.redis import redis_storage

        await redis_storage.close()
    except Exception:
        pass
    from app.db.session import close_db

    await close_db()
    logger.info("👋 Goodbye!")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="GlobalMediaCrawler",
        description=(
            "Multi-platform public content crawler and analysis system. "
            "Supports YouTube, Reddit, TikTok, Instagram, and X/Twitter."
        ),
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---- CORS Middleware ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Exception Handlers ----

    @app.exception_handler(PlatformNotSupportedError)
    async def platform_not_supported_handler(
        request: Request, exc: PlatformNotSupportedError
    ):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": str(exc),
                "message": "Platform not supported",
            },
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: RateLimitExceededError):
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": str(exc),
                "message": "Rate limit exceeded",
                "retry_after": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(QuotaExhaustedError)
    async def quota_exhausted_handler(request: Request, exc: QuotaExhaustedError):
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": str(exc),
                "message": "API quota exhausted",
            },
        )

    @app.exception_handler(CrawlerBaseError)
    async def crawler_error_handler(request: Request, exc: CrawlerBaseError):
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc), "message": "Crawler error"},
        )

    # ---- Register Routes (Phase 2 split routes) ----
    from app.api.routes.authors import router as authors_router
    from app.api.routes.comments import router as comments_router
    from app.api.routes.crawl import router as crawl_router
    from app.api.routes.health import router as health_router
    from app.api.routes.posts import router as posts_router
    from app.api.routes.tasks import router as tasks_router

    app.include_router(health_router, prefix="/api")
    app.include_router(posts_router, prefix="/api")
    app.include_router(authors_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(comments_router, prefix="/api")
    app.include_router(crawl_router, prefix="/api")

    return app


# Application instance
app = create_app()
