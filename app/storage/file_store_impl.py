"""
File-based store implementation (JSONL, CSV, JSON, Excel).
Follows the requested path structure: data/{platform}/{format}/{type}_{item}_{date}.{format}
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

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

    def _get_file_path(self, item_type: str) -> Path:
        """
        Generate path: {base}/{platform}/{subdir}/{crawler_type}_{item_type}_{date}.{format}
        subdir defaults to the format name (csv/json/etc), overridable via save_data_subdir.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        settings = get_settings()
        subdir = settings.save_data_subdir or self.file_type
        platform_dir = self.base_dir / self.platform / subdir
        platform_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.crawler_type}_{item_type}.{self.file_type}"
        return platform_dir / filename

    async def store_content(self, items: List[dict]):
        if not items: return
        path = self._get_file_path("contents")
        await self._write(path, items)

    async def store_comment(self, post_id: str, items: List[dict]):
        if not items: return
        # Add post_id to comments if not present
        for item in items:
            if "post_id" not in item:
                item["post_id"] = post_id
        
        path = self._get_file_path("comments")
        await self._write(path, items)

    async def store_creator(self, items: List[dict]):
        if not items: return
        path = self._get_file_path("creators")
        await self._write(path, items)

    async def _write(self, path: Path, items: List[dict]):
        if self.file_type == "jsonl":
            await self._write_jsonl(path, items)
        elif self.file_type == "csv":
            await self._write_csv(path, items)
        elif self.file_type == "json":
            await self._write_json(path, items)
        elif self.file_type == "excel":
            await self._write_excel(path, items)

    async def _write_jsonl(self, path: Path, items: List[dict]):
        with open(path, "a", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    async def _write_csv(self, path: Path, items: List[dict]):
        file_exists = path.exists()
        # Flatten nested fields for CSV
        flattened = []
        for item in items:
            flat = item.copy()
            for k, v in flat.items():
                if isinstance(v, (dict, list)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
            flattened.append(flat)

        if not flattened: return
        keys = flattened[0].keys()
        
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            if not file_exists:
                writer.writeheader()
            writer.writerows(flattened)

    async def _write_json(self, path: Path, items: List[dict]):
        existing_data = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except:
                pass
        
        existing_data.extend(items)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

    async def _write_excel(self, path: Path, items: List[dict]):
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
                except:
                    pass
            df.to_excel(path, index=False, engine="openpyxl")
        except ImportError:
            logger.error("pandas/openpyxl not installed for Excel export")

    async def close(self):
        pass
