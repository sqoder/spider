from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import (
    CrawlerBaseError,
    PlatformNotSupportedError,
    QuotaExhaustedError,
    RateLimitExceededError,
)
from app.core.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logger()
    settings = get_settings()

    logger.info("Starting GlobalMediaCrawler...")

    if settings.auto_create_tables:
        from app.db.session import init_db

        await init_db()
        logger.warning("AUTO_CREATE_TABLES is enabled. Use Alembic for normal development/production.")

    try:
        from app.storage.redis import redis_storage

        await redis_storage.connect()
        logger.info("Redis connected")
    except Exception as exc:
        logger.warning(f"Redis unavailable: {exc}")

    try:
        from app.core.rate_limiter import setup_rate_limiter

        setup_rate_limiter()
        logger.info("Rate limiter configured")
    except Exception as exc:
        logger.warning(f"Rate limiter setup skipped: {exc}")

    try:
        from app.crawlers.factory import register_all_crawlers

        register_all_crawlers()
        logger.info("Crawlers registered")
    except Exception as exc:
        logger.warning(f"Crawler registration skipped: {exc}")

    logger.info(f"GlobalMediaCrawler ready | env={settings.app_env}")

    yield

    logger.info("Shutting down GlobalMediaCrawler...")

    try:
        from app.storage.redis import redis_storage

        await redis_storage.close()
    except Exception:
        pass

    from app.db.session import close_db

    await close_db()
    logger.info("Goodbye!")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="GlobalMediaCrawler",
        description="Multi-platform public content crawler and analysis system.",
        version="0.2.1",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PlatformNotSupportedError)
    async def platform_not_supported_handler(request: Request, exc: PlatformNotSupportedError):
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
            content={
                "success": False,
                "error": str(exc),
                "message": "Crawler error",
            },
        )

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()
