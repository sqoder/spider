"""
File-based data storage (CSV/JSONL).
Handles saving crawled data to structured files in the data/ directory.
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List

from loguru import logger


class FileStorage:
    """Manages saving crawled data to CSV and JSONL files."""

    def __init__(self, base_dir: str = "data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_platform_dir(self, platform: str) -> Path:
        """Ensure and return the directory for a platform."""
        path = self.base_dir / platform
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_to_jsonl(self, platform: str, data: List[dict], filename: str = "posts.jsonl"):
        """Save a list of dictionaries to a JSONL file (append mode)."""
        platform_dir = self._get_platform_dir(platform)
        filepath = platform_dir / filename

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                for item in data:
                    # Add a timestamp for when it was saved to file
                    item["_file_saved_at"] = datetime.now().isoformat()
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            logger.info(f"Saved {len(data)} items to JSONL: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save JSONL for {platform}: {e}")

    def save_to_csv(self, platform: str, data: List[dict], filename: str = "posts.csv"):
        """Save a list of dictionaries to a CSV file (append mode)."""
        if not data:
            return

        platform_dir = self._get_platform_dir(platform)
        filepath = platform_dir / filename
        
        file_exists = filepath.exists()

        try:
            # Flatten some nested fields for CSV compatibility
            flattened_data = []
            for item in data:
                flat = item.copy()
                # Flatten metrics if they exist
                if "metrics" in flat and isinstance(flat["metrics"], dict):
                    for k, v in flat["metrics"].items():
                        flat[f"metric_{k}"] = v
                
                # Convert complex objects to strings
                for k, v in flat.items():
                    if isinstance(v, (dict, list)):
                        flat[k] = json.dumps(v, ensure_ascii=False)
                
                flat["_file_saved_at"] = datetime.now().isoformat()
                flattened_data.append(flat)

            if not flattened_data:
                return

            keys = flattened_data[0].keys()
            
            with open(filepath, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(flattened_data)
            
            logger.info(f"Saved {len(data)} items to CSV: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save CSV for {platform}: {e}")

    def save_to_excel(self, platform: str, data: List[dict], filename: str = "posts.xlsx"):
        """Save a list of dictionaries to an Excel file using pandas."""
        if not data:
            return

        try:
            import pandas as pd
        except ImportError:
            logger.warning("pandas/openpyxl not installed. Skipping Excel export.")
            return

        platform_dir = self._get_platform_dir(platform)
        filepath = platform_dir / filename

        try:
            # Prepare data
            flattened_data = []
            for item in data:
                flat = item.copy()
                if "metrics" in flat and isinstance(flat["metrics"], dict):
                    for k, v in flat["metrics"].items():
                        flat[f"metric_{k}"] = v
                for k, v in flat.items():
                    if isinstance(v, (dict, list)):
                        flat[k] = json.dumps(v, ensure_ascii=False)
                flat["_file_saved_at"] = datetime.now().isoformat()
                flattened_data.append(flat)

            df = pd.DataFrame(flattened_data)

            if filepath.exists():
                # Read existing and append
                try:
                    existing_df = pd.read_excel(filepath)
                    df = pd.concat([existing_df, df], ignore_index=True)
                except Exception as e:
                    logger.warning(f"Could not read existing Excel file {filepath}: {e}")

            df.to_excel(filepath, index=False, engine="openpyxl")
            logger.info(f"Saved {len(data)} items to Excel: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save Excel for {platform}: {e}")

    def save_comments_to_csv(self, platform: str, post_id: str, comments: List[dict], filename: str = "comments.csv"):
        """Save post comments to a separate CSV file."""
        if not comments:
            return

        platform_dir = self._get_platform_dir(platform)
        filepath = platform_dir / filename
        file_exists = filepath.exists()

        try:
            processed_comments = []
            for c in comments:
                processed = {
                    "post_id": post_id,
                    "comment_id": c.get("id"),
                    "author": c.get("author"),
                    "author_id": c.get("author_id"),
                    "text": c.get("text"),
                    "like_count": c.get("like_count"),
                    "timestamp": c.get("timestamp"),
                    "parent_id": c.get("parent", "root"), # "root" means top-level
                    "_file_saved_at": datetime.now().isoformat()
                }
                processed_comments.append(processed)

            keys = processed_comments[0].keys()
            with open(filepath, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(processed_comments)
            logger.info(f"Saved {len(comments)} comments to CSV: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save comments CSV for {platform}: {e}")

    def save_comments_to_excel(self, platform: str, post_id: str, comments: List[dict], filename: str = "comments.xlsx"):
        """Save post comments to a separate Excel file."""
        if not comments:
            return

        try:
            import pandas as pd
        except ImportError:
            return

        platform_dir = self._get_platform_dir(platform)
        filepath = platform_dir / filename

        try:
            processed_comments = []
            for c in comments:
                processed = {
                    "post_id": post_id,
                    "comment_id": c.get("id"),
                    "author": c.get("author"),
                    "author_id": c.get("author_id"),
                    "text": c.get("text"),
                    "like_count": c.get("like_count"),
                    "timestamp": c.get("timestamp"),
                    "parent_id": c.get("parent", "root"),
                    "_file_saved_at": datetime.now().isoformat()
                }
                processed_comments.append(processed)

            df = pd.DataFrame(processed_comments)

            if filepath.exists():
                try:
                    existing_df = pd.read_excel(filepath)
                    df = pd.concat([existing_df, df], ignore_index=True)
                except:
                    pass

            df.to_excel(filepath, index=False, engine="openpyxl")
            logger.info(f"Saved {len(comments)} comments to Excel: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save comments Excel for {platform}: {e}")


# Global file storage instance
file_storage = FileStorage()
