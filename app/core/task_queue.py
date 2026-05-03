"""
Celery task queue configuration for async crawl job processing.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "global_media_crawler",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Result expiry (24 hours)
    result_expires=86400,

    # Task routes
    task_routes={
        "app.workers.crawler_worker.execute_crawl_task": {"queue": "crawl"},
        "app.workers.crawler_worker.download_media": {"queue": "media"},
    },

    # Rate limits per task
    task_annotations={
        "app.workers.crawler_worker.execute_crawl_task": {
            "rate_limit": "10/m",
        },
    },

    # Retry policy
    task_default_retry_delay=60,
    task_max_retries=3,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers"])
