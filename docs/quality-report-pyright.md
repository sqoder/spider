## Type Checking Stabilization Report

All type checking and static analysis errors have been successfully addressed across the codebase.

### Resolved Areas:
1. **External Libraries Null-Safety:** Handled un-typed responses and dynamic attributes from `Scrapling` (`Fetcher`, `StealthyFetcher`), ensuring that `pyright` understands attributes like `.status_code`, `.page`, and `.find_similar()`.
2. **Type Casting and Guards:** Fixed missing or loose `source_id` typings in `app/storage/db_store_impl.py`, `app/crawlers/tiktok/crawler.py`, and `app/crawlers/x/crawler.py`.
3. **Celery Worker Redeclaration:** Fixed `crawler_worker.py` function redeclaration issues caused by branching.
4. **Test Suite:** Resolved `test_core.py` and `test_crawl_service.py` type hints where dummy classes and specific Pydantic `_env_file` parameters were causing noise.
5. **API & Pydantic Validation:** Handled type mappings in FastAPI route returns (`api/routes/posts.py`, `api/routes/tasks.py`) where SQLAlchemy models were directly returned into Pydantic paginated models.

### Current State:
The project is completely clean on pyright static type checks. The only warnings remaining relate to `wordcloud`, `jieba`, and `pandas` which are not installed in the virtual environment but do not impact the core crawler pipeline.
