"""
Celery task queue configuration for async crawl job processing.
In simple mode (SQLite/dev), Celery is disabled entirely.
"""

from app.core.config import get_settings

settings = get_settings()

# When SIMPLE_MODE is on or no broker URL, Celery is not needed
if settings.simple_mode or not settings.celery_broker_url:
    celery_app = None  # type: ignore
else:
    from celery import Celery

    celery_app = Celery(
        "global_media_crawler",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        result_expires=86400,
        task_routes={
            "app.workers.crawler_worker.execute_crawl_task": {"queue": "crawl"},
            "app.workers.crawler_worker.download_media": {"queue": "media"},
        },
        task_annotations={
            "app.workers.crawler_worker.execute_crawl_task": {
                "rate_limit": "10/m",
            },
        },
        task_default_retry_delay=60,
        task_max_retries=3,
    )

    # Auto-discover tasks
    celery_app.autodiscover_tasks(["app.workers"])
