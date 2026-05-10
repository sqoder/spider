# 1. 启用哪些平台（想抓哪个就取消哪个的注释，支持多个同时运行）
ENABLED_PLATFORMS = [
    "youtube",
    "reddit",
    # "tiktok",
    # "instagram",
    # "x",
]

# 2. 抓取模式选择：
# 可选值: "keyword"（关键词搜索） | "url"（抓取特定链接） | "user"（抓取特定博主/频道）
CRAWL_MODE = "keyword"

# --- [keyword 关键词搜索模式设置] ---
# 支持输入单个关键词或关键词列表，如: "apple" 或 ["apple", "huawei", "xiaomi"]
KEYWORDS = ["OpenAI", "AI agents", "LLM"]
LIMIT = 20  # 每个关键词抓取的视频数量

# --- [url 特定链接解析模式设置] ---
URLS = [
    # "https://www.youtube.com/watch?v=xxxxxxxxxxx",
]

# --- [user 频道/博主主页模式设置] ---
# 支持输入：博主的用户名/ID (如: "MrBeast") 或者是 博主的完整主页链接 (如: "https://www.youtube.com/@MrBeast")
USER_HANDLE = "MrBeast"
USER_POST_LIMIT = 10

# 3. 关联评论与详情抓取设置（适用于 keyword、url 和 user 用户主页模式）
DOWNLOAD_COMMENTS = True   # ✅ 开启评论抓取
COMMENTS_LIMIT = 9999      # 每帖抓取9999条评论
DOWNLOAD_REPLIES = True    # ✅ 开启二级回复抓取
# 评论排序：
#   "new" / "newest" → 按时间倒序，能抽取视频的全部历史评论（上万条起步）
#   "hot" / "top"    → 按热度排序，YouTube 服务端硬性封顶 ~1000-1500 条
# 想要"抓上万条"就保持 new，不要改成 hot。
COMMENTS_SORT = "new"

# 4. 关联媒体下载设置（是否下载高清视频、图片、音频、字幕等）
DOWNLOAD_MEDIA = True
# 下载媒体文件的过滤类型，支持: "video" (视频) | "image" (图片/封面) | "subtitle" (字幕)
MEDIA_TYPES = ["video", "image", "subtitle"]
# 视频下载的分辨率/画质，支持: 360 | 720 | 1080 | 1440 | 2160 (等数字)
MEDIA_QUALITY = 360

# 5. 存储格式与路径设置
# 支持的格式: "csv" | "jsonl" | "database"（保存至 SQLite/Postgres 数据库）
SAVE_FORMAT = "jsonl"
SAVE_PATH = "./data"  # 统一数据存储目录

# 数据库连接设置（当 SAVE_FORMAT = "database" 时生效，支持 SQLite 或 PostgreSQL）
# 示例一 (SQLite 极简本地数据库): "sqlite+aiosqlite:///./data/db/crawler.db"
# 示例二 (PostgreSQL 高并发数据库): "postgresql+asyncpg://crawler:crawler_pass@localhost:5432/global_media_crawler"
DATABASE_URI = "sqlite+aiosqlite:///./data/db/crawler.db"

# 6. 爬虫速率与并发限制（防封锁、防爆频保护）
REQUEST_DELAY = 5.0       # 抓全部评论需要更长延迟
MAX_RETRIES = 5           # 增加重试次数，确保数据完整
CONCURRENT_LIMIT = 1      # 单并发避免触发限流

# 7. 代理服务设置（可选，防止 platform 封锁 IP）
PROXY_URL = ""         # 代理服务器地址（如: "http://127.0.0.1:7890"，为空代表直连）
PROXY_ROTATION = False # 是否开启动态住宅代理 Session ID 每次请求自动换 IP 轮换

# 8. 平台 API 密钥与 Cookie 凭证设置
# ⚠️  机密字段已迁移到 .env（避免 git 提交泄漏）。
#     YOUTUBE_API_KEY / REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET 请写在项目根目录的 .env 文件里。
#     示例：
#         YOUTUBE_API_KEY=AIza...
#         REDDIT_CLIENT_ID=xxx
#         REDDIT_CLIENT_SECRET=xxx
YOUTUBE_DAILY_QUOTA = 10000
YOUTUBE_USE_SCRAPER = True  #  开启Playwright浏览器模式，不使用API
YOUTUBE_COOKIES_FILE = "youtube_cookies.txt"  # YouTube登录Cookie（可选）

REDDIT_USER_AGENT = "GlobalMediaCrawler/1.0"

TIKTOK_COOKIES_FILE = ""  # TikTok Cookie（可选，用于登录状态）
INSTAGRAM_COOKIES_FILE = ""  # Instagram Cookie（可选）
X_ACCOUNTS_FILE = ""  # X/Twitter账号文件（可选）

# 9. 细粒度速率限制设置 (Rate Limiting)
# 单位：次数/时间窗口(秒)
# 浏览器模式可以适当提高限制
DEFAULT_RATE_LIMIT = 30
DEFAULT_RATE_PERIOD = 60

YOUTUBE_RATE_LIMIT = 20     # Playwright模式：每分钟20次请求
YOUTUBE_RATE_PERIOD = 60

REDDIT_RATE_LIMIT = 30      # Public JSON爬虫：每分钟30次请求
REDDIT_RATE_PERIOD = 60

TIKTOK_RATE_LIMIT = 15      # TikTok浏览器模式：每分钟15次请求
TIKTOK_RATE_PERIOD = 60

# 10. 系统与后台服务设置 (System & Backend)
SIMPLE_MODE = True        # 极简模式：禁用 Redis/Celery 依赖，仅使用本地存储 (True/False)
DATA_DIR = "data"         # 数据存储根目录

# Redis 连接设置 (仅在 SIMPLE_MODE = False 时生效)
REDIS_URL = "redis://localhost:6379/0"

# Celery 任务队列设置 (仅在 SIMPLE_MODE = False 时生效)
CELERY_BROKER_URL = "redis://localhost:6379/1"
CELERY_RESULT_BACKEND = "redis://localhost:6379/2"
