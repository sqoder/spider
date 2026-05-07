"""
Visual analysis service.
Generates word clouds and other visualizations from crawled data.
"""

import os
from pathlib import Path

from loguru import logger


class VisualService:
    """Service for data visualization."""

    def __init__(self, output_dir: str = "data/visual"):
        self.output_dir = Path(output_dir)

    def generate_word_cloud(self, text: str, output_filename: str) -> Path | None:
        """
        Generate a word cloud from text.

        Args:
            text: The text to process
            output_filename: Filename to save the image (e.g., 'wordcloud.png')

        Returns:
            Path to the generated image, or None if failed
        """
        if not text:
            logger.warning("No text provided for word cloud.")
            return None

        try:
            import jieba
            from wordcloud import WordCloud
        except ImportError:
            logger.warning(
                "wordcloud/matplotlib/jieba not installed. Skipping word cloud generation."
            )
            return None

        try:
            # Process text (especially for Chinese)
            words = jieba.cut(text)
            processed_text = " ".join(words)

            # Generate word cloud
            # Use a default font that supports Chinese if possible, or fallback to default
            font_path = self._find_font()

            wc = WordCloud(
                font_path=font_path,
                width=1200,
                height=800,
                background_color="white",
                max_words=200,
                collocations=False,
            )
            wc.generate(processed_text)

            # Save
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.output_dir / output_filename
            wc.to_file(str(output_path))

            logger.info(f"Word cloud generated: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to generate word cloud: {e}")
            return None

    def _find_font(self) -> str | None:
        """Try to find a suitable font path for word cloud (supporting Chinese)."""
        # Common locations for fonts on different systems
        paths = [
            "/System/Library/Fonts/PingFang.ttc",  # macOS
            "/System/Library/Fonts/STHeiti Light.ttc",  # macOS
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
            "C:\\Windows\\Fonts\\msyh.ttc",  # Windows
            "C:\\Windows\\Fonts\\simhei.ttf",  # Windows
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return None


# Global visual service instance
visual_service = VisualService()
