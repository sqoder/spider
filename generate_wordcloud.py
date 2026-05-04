"""
CLI tool to generate a word cloud from saved comments CSV.
Usage: python generate_wordcloud.py youtube/comments.csv
"""

import sys
import pandas as pd
from pathlib import Path
from app.services.visual_service import visual_service
from loguru import logger

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_wordcloud.py [platform/filename.csv]")
        print("Example: python generate_wordcloud.py youtube/comments.csv")
        return

    file_path = Path("data") / sys.argv[1]
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return

    try:
        # Load data
        logger.info(f"Loading data from {file_path}...")
        df = pd.read_csv(file_path)
        
        # Check for text column
        text_col = None
        for col in ["text", "content", "body"]:
            if col in df.columns:
                text_col = col
                break
        
        if not text_col:
            logger.error(f"Could not find text column in {file_path}. Available columns: {df.columns.tolist()}")
            return

        # Combine all text
        text = " ".join(df[text_col].dropna().astype(str).tolist())
        
        # Generate word cloud
        output_name = f"{file_path.stem}_wordcloud.png"
        visual_service.generate_word_cloud(text, output_name)
        
    except Exception as e:
        logger.error(f"Failed to generate word cloud: {e}")

if __name__ == "__main__":
    main()
