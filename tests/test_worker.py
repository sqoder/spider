from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.crawler_worker import _execute_task_async


@pytest.mark.asyncio
async def test_execute_task_async_not_found():
    with (
        patch("app.repositories.task_repo.TaskRepository.get_by_id", return_value=None),
        patch("app.db.session.get_session_factory") as mock_session_factory,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.return_value.__aenter__.return_value = mock_session

        # Should return early without crashing
        await _execute_task_async(999)


@pytest.mark.asyncio
async def test_execute_task_async_success():
    task_id = 1
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.platform = "youtube"
    mock_task.task_type = "search"
    mock_task.keyword = "test"
    mock_task.limit_count = 5
    mock_task.params = {}

    with (
        patch("app.repositories.task_repo.TaskRepository") as MockTaskRepo,
        patch("app.crawlers.factory.CrawlerFactory.create") as MockCrawlerFactory,
        patch("app.storage.factory.StoreFactory.create_store") as MockStoreFactory,
        patch("app.db.session.get_session_factory") as mock_session_factory,
        patch("app.storage.redis.redis_storage.set_task_progress", new_callable=AsyncMock),
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.return_value.__aenter__.return_value = mock_session

        task_repo = MockTaskRepo.return_value
        task_repo.get_by_id = AsyncMock(return_value=mock_task)
        task_repo.mark_running = AsyncMock()
        task_repo.mark_success = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.search.return_value = []
        MockCrawlerFactory.return_value = mock_crawler

        mock_store = AsyncMock()
        MockStoreFactory.return_value = mock_store

        await _execute_task_async(task_id)

        task_repo.mark_running.assert_awaited_once_with(task_id)
        task_repo.mark_success.assert_awaited_once()
        mock_crawler.close.assert_awaited()
        mock_store.close.assert_awaited()


@pytest.mark.asyncio
async def test_execute_task_async_failure():
    task_id = 1
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.platform = "youtube"
    mock_task.task_type = "search"
    mock_task.keyword = "test"
    mock_task.limit_count = 5

    with (
        patch("app.repositories.task_repo.TaskRepository") as MockTaskRepo,
        patch("app.crawlers.factory.CrawlerFactory.create") as MockCrawlerFactory,
        patch("app.db.session.get_session_factory") as mock_session_factory,
        patch("app.storage.redis.redis_storage.set_task_progress", new_callable=AsyncMock),
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.return_value.__aenter__.return_value = mock_session

        task_repo = MockTaskRepo.return_value
        task_repo.get_by_id = AsyncMock(return_value=mock_task)
        task_repo.mark_running = AsyncMock()
        task_repo.mark_failed = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.search.side_effect = Exception("Crawl failed")
        MockCrawlerFactory.return_value = mock_crawler

        with pytest.raises(Exception, match="Crawl failed"):
            await _execute_task_async(task_id)

        task_repo.mark_failed.assert_awaited_once()
