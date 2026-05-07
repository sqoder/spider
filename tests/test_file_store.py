import json

import pytest

from app.core.config import get_settings
from app.storage.file_store_impl import FileStoreImplement


@pytest.mark.asyncio
async def test_jsonl_store_writes_content(tmp_path, monkeypatch):
    monkeypatch.setenv("SAVE_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("SAVE_DATA_OPTION", "jsonl")
    monkeypatch.setenv("SAVE_DATA_SUBDIR", "")
    get_settings.cache_clear()

    store = FileStoreImplement("youtube", "search", "jsonl")
    await store.store_content([{"source_id": "v1", "title": "Video"}])

    path = tmp_path / "youtube" / "jsonl" / "search_contents.jsonl"
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"source_id": "v1", "title": "Video"}]
