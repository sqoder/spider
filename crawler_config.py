

# 1. 启用哪些平台（想抓哪个就取消哪个的注释，支持多个同时运行）
ENABLED_PLATFORMS = [
    # "youtube",
    "reddit",
    # "tiktok",
    # "instagram",
    # "x",
]

# 2. 抓取模式选择：
# 可选值: "keyword"（关键词搜索） | "url"（抓取特定链接） | "user"（抓取特定博主/频道）
CRAWL_MODE = "keyword"

# --- [keyword 关键词搜索模式设置] ---
KEYWORD = "huawei"
LIMIT = 5

# --- [url 特定链接解析模式设置] ---
URLS = [
    # "https://www.youtube.com/watch?v=xxxxxxxxxxx",
]

# --- [user 频道/博主主页模式设置] ---
# 支持输入：博主的用户名/ID (如: "MrBeast") 或者是 博主的完整主页链接 (如: "https://www.youtube.com/@MrBeast")
USER_HANDLE = "MrBeast"
USER_POST_LIMIT = 10

# 3. 关联评论与详情抓取设置（适用于 keyword、url 和 user 用户主页模式）
DOWNLOAD_COMMENTS = True
COMMENTS_LIMIT = 20
DOWNLOAD_REPLIES = True  # 是否抓取评论的二级子回复 (True/False)
COMMENTS_SORT = "hot"     # 评论排序逻辑: "hot" (热门评论) | "new" (最新评论)

# 4. 关联媒体下载设置（是否下载高清视频、图片、音频、字幕等）
DOWNLOAD_MEDIA = True
# 下载媒体文件的过滤类型，支持: "video" (视频) | "image" (图片/封面) | "subtitle" (字幕)
MEDIA_TYPES = ["video", "image", "subtitle"]
# 视频下载的分辨率/画质，支持: 360 | 720 | 1080 | 1440 | 2160 (等数字)
MEDIA_QUALITY = 360

# 5. 存储格式与路径设置
# 支持的格式: "csv" | "jsonl" | "database"（保存至 SQLite/Postgres 数据库）
SAVE_FORMAT = "jsonl"
SAVE_PATH = "./output"

# 数据库连接设置（当 SAVE_FORMAT = "database" 时生效，支持 SQLite 或 PostgreSQL）
# 示例一 (SQLite 极简本地数据库): "sqlite+aiosqlite:///./data/crawler.db"
# 示例二 (PostgreSQL 高并发数据库): "postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler"
DATABASE_URI = "sqlite+aiosqlite:///./data/crawler.db"

# 6. 爬虫速率与并发限制（防封锁、防爆频保护）
REQUEST_DELAY = 1.0       # 每次请求之间的强制睡眠延迟秒数（防止请求过快触发反爬）
MAX_RETRIES = 5           # 网络请求失败时的自动最大重试次数
CONCURRENT_LIMIT = 3      # Playwright 浏览器实例或并发请求的最大数量上限

# 7. 代理服务设置（可选，防止 platform 封锁 IP）
PROXY_URL = ""         # 代理服务器地址（如: "http://127.0.0.1:7890"，为空代表直连）
PROXY_ROTATION = False # 是否开启动态住宅代理 Session ID 每次请求自动换 IP 轮换

# 8. 平台 API 密钥与 Cookie 凭证设置（可选，部分平台需要 API Key 或 Cookie 才能高阶登录抓取）
YOUTUBE_API_KEY = ""
YOUTUBE_DAILY_QUOTA = 10000 # YouTube API 每日免费配额上限（默认 10000）
YOUTUBE_USE_SCRAPER = False # 是否使用 Playwright 爬虫模式替代 API（默认 False，API 更稳定）
YOUTUBE_COOKIES_FILE = "youtube_cookies.txt"

REDDIT_CLIENT_ID = ""
REDDIT_CLIENT_SECRET = ""
REDDIT_USER_AGENT = "GlobalMediaCrawler/1.0"

TIKTOK_COOKIES_FILE = ""
INSTAGRAM_COOKIES_FILE = ""
X_ACCOUNTS_FILE = ""

# 9. 细粒度速率限制设置 (Rate Limiting)
# 单位：次数/时间窗口(秒)
DEFAULT_RATE_LIMIT = 30
DEFAULT_RATE_PERIOD = 60

YOUTUBE_RATE_LIMIT = 50
YOUTUBE_RATE_PERIOD = 60

REDDIT_RATE_LIMIT = 90
REDDIT_RATE_PERIOD = 60

TIKTOK_RATE_LIMIT = 20
TIKTOK_RATE_PERIOD = 60

# 10. 系统与后台服务设置 (System & Backend)
SIMPLE_MODE = True        # 极简模式：禁用 Redis/Celery 依赖，仅使用本地存储 (True/False)
DATA_DIR = "data"         # 数据存储根目录

# Redis 连接设置 (仅在 SIMPLE_MODE = False 时生效)
REDIS_URL = "redis://localhost:6379/0"

# Celery 任务队列设置 (仅在 SIMPLE_MODE = False 时生效)
CELERY_BROKER_URL = "redis://localhost:6379/1"
CELERY_RESULT_BACKEND = "redis://localhost:6379/2"
