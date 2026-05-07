"""
File-based store implementation (JSONL, CSV, JSON, Excel).
Follows the requested path structure: data/{platform}/{format}/{type}_{item}_{date}.{format}
"""

import csv
import json
from pathlib import Path

import anyio
from loguru import logger

from app.core.config import get_settings
from app.storage.base_store import BaseStore


class FileStoreImplement(BaseStore):
    """Implementation for file-based storage."""

    def __init__(self, platform: str, crawler_type: str, file_type: str):
        super().__init__(platform, crawler_type)
        self.file_type = file_type.lower()
        settings = get_settings()
        self.base_dir = Path(settings.save_data_path)

    async def _get_file_path(self, item_type: str) -> Path:
        """
        Generate path: {base}/{platform}/{subdir}/{crawler_type}_{item_type}_{date}.{format}
        subdir defaults to the format name (csv/json/etc), overridable via save_data_subdir.
        """
        settings = get_settings()
        subdir = settings.save_data_subdir or self.file_type
        platform_dir = self.base_dir / self.platform / subdir

        def _mkdir():
            platform_dir.mkdir(parents=True, exist_ok=True)

        await anyio.to_thread.run_sync(_mkdir)

        filename = f"{self.crawler_type}_{item_type}.{self.file_type}"
        return platform_dir / filename

    async def store_content(self, items: list[dict]):
        if not items:
            return
        path = await self._get_file_path("contents")
        await self._write(path, items)

    async def store_comment(self, post_id: str, items: list[dict]):
        if not items:
            return
        # Add post_id to comments if not present
        for item in items:
            if "post_id" not in item:
                item["post_id"] = post_id

        path = await self._get_file_path("comments")
        await self._write(path, items)

    async def store_creator(self, items: list[dict]):
        if not items:
            return
        path = await self._get_file_path("creators")
        await self._write(path, items)

    async def _write(self, path: Path, items: list[dict]):
        if self.file_type == "jsonl":
            await self._write_jsonl(path, items)
        elif self.file_type == "csv":
            await self._write_csv(path, items)
        elif self.file_type == "json":
            await self._write_json(path, items)
        elif self.file_type == "excel":
            await self._write_excel(path, items)

    async def _write_jsonl(self, path: Path, items: list[dict]):
        def _sync_write_jsonl():
            with open(path, "a", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

        await anyio.to_thread.run_sync(_sync_write_jsonl)

    async def _write_csv(self, path: Path, items: list[dict]):
        def _sync_write_csv():
            file_exists = path.exists()
            # Flatten nested fields for CSV
            flattened = []
            for item in items:
                flat = item.copy()
                for k, v in flat.items():
                    if isinstance(v, (dict, list)):
                        flat[k] = json.dumps(v, ensure_ascii=False)
                flattened.append(flat)

            if not flattened:
                return
            keys = flattened[0].keys()

            with open(path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(flattened)

        await anyio.to_thread.run_sync(_sync_write_csv)

    async def _write_json(self, path: Path, items: list[dict]):
        def _sync_write_json():
            existing_data = []
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception:
                    pass

            existing_data.extend(items)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

        await anyio.to_thread.run_sync(_sync_write_json)

    async def _write_excel(self, path: Path, items: list[dict]):
        def _sync_write_excel():
            try:
                import pandas as pd

                # Flatten for excel
                flattened = []
                for item in items:
                    flat = item.copy()
                    for k, v in flat.items():
                        if isinstance(v, (dict, list)):
                            flat[k] = json.dumps(v, ensure_ascii=False)
                    flattened.append(flat)

                df = pd.DataFrame(flattened)
                if path.exists():
                    try:
                        existing_df = pd.read_excel(path)
                        df = pd.concat([existing_df, df], ignore_index=True)
                    except Exception:
                        pass
                df.to_excel(path, index=False, engine="openpyxl")
            except ImportError:
                logger.error("pandas/openpyxl not installed for Excel export")

        await anyio.to_thread.run_sync(_sync_write_excel)

    async def close(self):
        pass
