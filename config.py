# ============================================
# YouTube Crawl Configuration
# Edit this file to control crawl behavior.
# ============================================

# --- Crawl Mode ---
# "keyword"  = search by keyword
# "url"      = crawl specific video URLs
# "user"     = crawl all videos from a user/channel
CRAWL_MODE = "keyword"

# --- Keyword Search Mode ---
# Used when CRAWL_MODE = "keyword"
SEARCH_KEYWORD = "内马尔"
SEARCH_LIMIT = 5

# --- URL Crawl Mode ---
# Used when CRAWL_MODE = "url"
CRAWL_URLS = [
    "https://www.youtube.com/watch?v=xxxxxxxxxxx",
]

# --- User Crawl Mode ---
# Used when CRAWL_MODE = "user"
USER_HANDLE = "MrBeast"        # YouTube handle (without @)
USER_POST_LIMIT = 5

# --- Comment Settings ---
COMMENTS_ENABLED = True       # False = skip comments entirely
COMMENTS_COUNT = 100          # 评论数量（设大数如 99999 就是全部抓完）
INCLUDE_REPLIES = True        # True = 一二级评论全抓，False = 仅一级

# --- Media Settings ---
MEDIA_ENABLED = True           # Enable/disable thumbnail + video download
MEDIA_QUALITY = 360            # Video quality (360, 720, 1080)
