"""
Celery worker tasks for async crawl job execution.
"""

import asyncio
from typing import Optional

from loguru import logger

from app.core.task_queue import celery_app
from app.crawlers.factory import CrawlerFactory, register_all_crawlers

# Register crawlers when worker starts
register_all_crawlers()


def _run_async(coro):
    """Helper to run async code in Celery worker."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # This shouldn't happen in a standard Celery worker, 
        # but if it does, we need to run it in a thread or use nest_asyncio
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    else:
        try:
            return loop.run_until_complete(coro)
        finally:
            # Don't close the loop, reuse it for the next task in this process
            pass


@celery_app.task(
    bind=True,
    name="app.workers.crawler_worker.execute_crawl_task",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def execute_crawl_task(self, task_id: int):
    """
    Execute a crawl task by ID.
    Reads task params from DB, runs the crawler, and saves results.
    """
    logger.info(f"Executing crawl task: {task_id}")

    try:
        _run_async(_execute_task_async(task_id))
    except Exception as e:
        logger.error(f"Crawl task {task_id} failed: {e}")
        # Update task status to failed
        _run_async(_update_task_failed(task_id, str(e)))
        # Retry if attempts remaining
        raise self.retry(exc=e)


async def _execute_task_async(task_id: int):
    """Async implementation of crawl task execution."""
    from app.db.session import get_session_factory
    from app.repositories.author_repo import AuthorRepository
    from app.repositories.comment_repo import CommentRepository
    from app.repositories.post_repo import PostRepository
    from app.repositories.task_repo import TaskRepository
    from app.schemas.author import AuthorCreate
    from app.schemas.comment import CommentCreate
    from app.schemas.post import PostCreate
    from app.storage.redis import redis_storage

    session_factory = get_session_factory()
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        post_repo = PostRepository(session)
        author_repo = AuthorRepository(session)
        comment_repo = CommentRepository(session)

        # Load task
        task = await task_repo.get_by_id(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        # Update status to running
        await task_repo.mark_running(task_id)

        # Update progress in Redis
        try:
            await redis_storage.set_task_progress(
                task_id,
                {
                    "status": "running",
                    "items_crawled": 0,
                },
            )
        except Exception:
            pass

        try:
            # Create crawler
            crawler = CrawlerFactory.create(task.platform)
            results = []

            # Execute based on task type
            if task.task_type == "search":
                results = await crawler.search(task.keyword, limit=task.limit_count)

            elif task.task_type == "user_posts":
                results = await crawler.get_user_posts(
                    task.username, limit=task.limit_count
                )

            elif task.task_type in ("post_detail", "url_parse"):
                result = await crawler.get_post_detail(task.url)
                results = [result]

            elif task.task_type == "comments":
                # Get post_id from task params
                post_id_str = (task.params or {}).get("post_id", "")
                db_post_id = (task.params or {}).get("db_post_id")

                comments = await crawler.get_comments(
                    post_id_str, limit=task.limit_count
                )

                if db_post_id:
                    for c in comments:
                        comment_data = CommentCreate(
                            platform=c.platform,
                            source_id=c.source_id,
                            post_id=db_post_id,
                            author_name=c.author_name,
                            author_source_id=c.author_id,
                            content=c.content,
                            like_count=c.like_count,
                            reply_count=c.reply_count,
                            parent_comment_id=c.parent_comment_id,
                            published_at=c.published_at,
                            raw_data=c.raw,
                        )
                        await comment_repo.create_or_update(comment_data)

                await task_repo.mark_success(task_id, success_count=len(comments))
                await crawler.close()
                return

            # Unified storage via factory
            from app.storage.factory import StoreFactory
            store = StoreFactory.create_store(task.platform, task.task_type)
            
            try:
                # 1. Store main contents
                if task.task_type != "comments":
                    results_dicts = [r.to_dict() for r in results]
                    await store.store_content(results_dicts)
                    
                    # Store authors
                    authors = [r.to_dict().get("author") for r in results if r.to_dict().get("author")]
                    if authors:
                        await store.store_creator(authors)
                
                # 2. Store comments (either from post detail or explicit comment task)
                if task.task_type == "comments":
                    post_id_str = (task.params or {}).get("post_id", "")
                    await store.store_comment(post_id_str, [c.to_dict() for c in results])
                else:
                    for r in results:
                        if r.raw.get("comments"):
                            await store.store_comment(r.source_id, r.raw["comments"])

                # 3. Handle media downloads and completion tracking
                saved_count = len(results)
                for r in results:
                    if task.task_type in ("post_detail", "url_parse"):
                        try:
                            from app.workers.crawler_worker import download_media
                            download_media.delay(task.platform, task.url, r.source_id)
                        except Exception as e:
                            logger.error(f"Failed to queue media download for {r.source_id}: {e}")
            finally:
                await store.close()

            # Update task as completed
            await task_repo.mark_success(task_id, success_count=saved_count)

            # Update Redis progress
            try:
                await redis_storage.set_task_progress(
                    task_id,
                    {
                        "status": "completed",
                        "items_crawled": saved_posts,
                    },
                )
            except Exception:
                pass

        except Exception as e:
            await task_repo.mark_failed(task_id, error_message=str(e))
            raise
        finally:
            try:
                from app.db.session import close_db
                await close_db()
            except Exception:
                pass
            
            try:
                if 'crawler' in locals():
                    await crawler.close()
            except Exception:
                pass
            
            logger.info(f"Task {task_id} execution finished")


async def _update_task_failed(task_id: int, error: str):
    """Update task status to failed."""
    from app.db.session import get_session_factory
    from app.repositories.task_repo import TaskRepository

    session_factory = get_session_factory()
    async with session_factory() as session:
        task_repo = TaskRepository(session)
        await task_repo.mark_failed(task_id, error_message=error)


@celery_app.task(
    name="app.workers.crawler_worker.download_media",
    max_retries=2,
    default_retry_delay=120,
)
def download_media(platform: str, url: str, source_id: str):
    """Download media for a specific post."""
    logger.info(f"Downloading media: {platform}/{source_id}")

    try:
        # Create a new loop for each media download task to avoid cross-loop issues
        asyncio.run(_download_media_async(platform, url, source_id))
    except Exception as e:
        logger.error(f"Media download failed for {source_id}: {e}")


async def _download_media_async(platform: str, url: str, source_id: str):
    """Async media download implementation."""
    from app.storage.media_storage import media_storage

    if media_storage.file_exists(platform, source_id):
        logger.info(f"Media already exists: {platform}/{source_id}")
        return

    if not media_storage.has_space():
        logger.warning("Storage full, cleaning up old files")
        media_storage.cleanup_oldest()

    if platform in ("youtube", "tiktok"):
        from app.crawlers.youtube.ytdlp_client import YtdlpClient

        client = YtdlpClient()
        # Use a dedicated folder for each post to capture all assets (video, thumb, json, subs)
        post_dir = media_storage.get_post_media_dir(platform, source_id)
        output = str(post_dir / "video")
        await client.download_video(url, output_template=output)

    elif platform in ("instagram",):
        from app.crawlers.tiktok.gallerydl_client import GalleryDLClient

        client = GalleryDLClient(platform=platform)
        await client.download(
            url, output_dir=str(media_storage.get_platform_dir(platform))
        )

    logger.info(f"Media downloaded: {platform}/{source_id}")
