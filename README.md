# GlobalMediaCrawler

> 多平台公开内容采集与分析系统 — 国外版 MediaCrawler

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🌐 支持平台

| 平台 | 阶段 | 搜索 | 用户主页 | 单条解析 | 评论 | 媒体下载 |
|------|------|:----:|:-------:|:-------:|:----:|:-------:|
| **YouTube** | 第一期 ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Reddit** | 第一期 ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **TikTok** | 第一期 ✅ | ⚠️ | ✅ | ✅ | ❌ | ✅ |
| **Instagram** | 第二期 | ⚠️ | ✅ | ✅ | ❌ | ✅ |
| **X / Twitter** | 第三期 | ⚠️ | ⚠️ | ✅ | ❌ | ❌ |

> ✅ 完整支持 | ⚠️ 有限支持 | ❌ 暂不支持

## 🏗️ 技术栈

- **后端框架**: FastAPI + Uvicorn
- **数据库**: PostgreSQL (异步, SQLAlchemy 2.0)
- **缓存**: Redis
- **任务队列**: Celery
- **采集工具**: YouTube Data API / yt-dlp / gallery-dl / twscrape
- **容器化**: Docker + Docker Compose

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/yourname/global-media-crawler.git
cd global-media-crawler

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 3. 启动所有服务
docker-compose up -d

# 4. 查看服务状态
docker-compose ps

# 5. 访问 API 文档
open http://localhost:8000/docs
```

### 方式二：本地开发

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # macOS/Linux

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env

# 4. 启动 PostgreSQL 和 Redis（可以用 Docker）
docker-compose up -d postgres redis

# 5. 启动 FastAPI 服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. （另一个终端）启动 Celery Worker
celery -A app.core.task_queue:celery_app worker --loglevel=info -Q crawl,media
```

## 📡 API 使用

### 健康检查

```bash
curl http://localhost:8000/api/health
```

### 关键词搜索（同步）

```bash
curl -X POST http://localhost:8000/api/crawl/search \
  -H "Content-Type: application/json" \
  -d '{"platform": "youtube", "keyword": "AI tools", "limit": 10}'
```

### 用户主页采集（同步）

```bash
curl -X POST http://localhost:8000/api/crawl/user \
  -H "Content-Type: application/json" \
  -d '{"platform": "reddit", "username": "spez", "limit": 10}'
```

### 单条 URL 解析（同步）

```bash
curl -X POST http://localhost:8000/api/crawl/url \
  -H "Content-Type: application/json" \
  -d '{"platform": "youtube", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### 创建异步任务

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"platform": "youtube", "type": "search", "keyword": "AI tools", "limit": 20}'
```

### 查询任务状态

```bash
curl http://localhost:8000/api/tasks/1
```

### 获取已采集内容

```bash
# 全部
curl "http://localhost:8000/api/posts?page=1&page_size=20"

# 按平台筛选
curl "http://localhost:8000/api/posts?platform=youtube&page=1"
```

## 📁 项目结构

```
global-media-crawler/
├── app/
│   ├── main.py                  # FastAPI 应用入口
│   ├── api/
│   │   └── routes.py            # API 路由定义
│   ├── core/
│   │   ├── config.py            # 配置管理
│   │   ├── logger.py            # 日志系统
│   │   ├── rate_limiter.py      # 速率限制器
│   │   ├── task_queue.py        # Celery 配置
│   │   ├── proxy_manager.py     # 代理管理
│   │   └── exceptions.py        # 自定义异常
│   ├── crawlers/
│   │   ├── base.py              # 爬虫基类 (BaseCrawler)
│   │   ├── factory.py           # 爬虫工厂 (CrawlerFactory)
│   │   ├── youtube/
│   │   │   ├── crawler.py       # YouTube 爬虫
│   │   │   ├── api_client.py    # YouTube Data API 客户端
│   │   │   └── ytdlp_client.py  # yt-dlp 封装
│   │   ├── reddit/
│   │   │   ├── crawler.py       # Reddit 爬虫
│   │   │   └── api_client.py    # Reddit OAuth API 客户端
│   │   ├── tiktok/
│   │   │   ├── crawler.py       # TikTok 爬虫
│   │   │   └── gallerydl_client.py  # gallery-dl 封装
│   │   ├── instagram/
│   │   │   └── crawler.py       # Instagram 爬虫
│   │   └── x/
│   │       └── crawler.py       # X/Twitter 爬虫
│   ├── models/
│   │   ├── database.py          # SQLAlchemy 数据库配置
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── post.py              # Post 数据模型
│   │   ├── author.py            # Author 数据模型
│   │   ├── comment.py           # Comment 数据模型
│   │   └── task.py              # CrawlTask 数据模型
│   ├── storage/
│   │   ├── postgres.py          # PostgreSQL CRUD 操作
│   │   ├── redis.py             # Redis 缓存操作
│   │   └── media_storage.py     # 媒体文件存储
│   └── workers/
│       └── crawler_worker.py    # Celery 异步任务
├── tests/
│   ├── test_core.py             # 核心模块测试
│   ├── test_crawlers.py         # 爬虫基类测试
│   ├── test_api.py              # API 端点测试
│   ├── test_youtube.py          # YouTube 解析测试
│   └── test_reddit.py           # Reddit 解析测试
├── alembic/                     # 数据库迁移
├── docker-compose.yml           # Docker 编排
├── Dockerfile                   # 容器构建
├── requirements.txt             # Python 依赖
├── pyproject.toml               # 项目配置
└── .env.example                 # 环境变量模板
```

## ⚙️ 环境变量

### 必填项

| 变量 | 说明 | 示例 |
|------|------|------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 密钥 | `AIzaSy...` |
| `REDDIT_CLIENT_ID` | Reddit OAuth App ID | `abc123...` |
| `REDDIT_CLIENT_SECRET` | Reddit OAuth App Secret | `xyz789...` |

### 可选项

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` |
| `PROXY_URL` | HTTP 代理地址 | 无 |
| `YOUTUBE_DAILY_QUOTA` | YouTube API 每日配额 | `10000` |
| `MEDIA_STORAGE_PATH` | 媒体文件存储路径 | `./media` |
| `TIKTOK_COOKIES_FILE` | TikTok cookies 文件路径 | 无 |

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_youtube.py -v

# 带覆盖率
pytest --cov=app --cov-report=html
```

## 📊 监控

- **API 文档**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Flower (Celery 监控)**: http://localhost:5555

## 🗄️ 数据库迁移

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "add new field"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

## 🔐 合规声明

本项目仅用于学习和研究目的，采集公开可访问的内容。使用时请：

1. 遵守各平台的服务条款 (Terms of Service)
2. 尊重 robots.txt 规则
3. 合理控制请求频率，避免对目标服务造成压力
4. 不采集私密或受限内容
5. 遵守当地法律法规关于数据采集的规定

## 📝 License

MIT License
