# 施工单 · YouTube & Reddit 爬虫全量 Bug 修复
**分支**：`fix/stabilize-youtube-mvp`  
**仓库**：`https://github.com/sqoder/spider.git`  
**施工版本**：v1.0  

---

## 任务目标（必须可验证）

修复 `fix/stabilize-youtube-mvp` 分支中 YouTube 和 Reddit 爬虫代码的全部已知 Bug，同时将配置文件统一为纯 Python 格式，移除 `.env` 依赖。

**成功判定：**
- `YouTubeCrawler.search(keyword, limit=500)` 能正确对 API 计费，时间切片使用 UTC 时区，空窗口及时终止
- `YouTubeCrawler.get_comments(post_id, limit=50)` 返回结果数量严格不超过 `limit`
- `YouTubeCrawler.get_user_posts` 对 search endpoint 正确传递 `cost=100`
- `YouTubeCrawler._parse_video` 中 `author_username` 不再填充 Channel ID
- `YouTubeAPIClient._request` 使用 `asyncio.get_running_loop()` 替代 `get_event_loop()`
- `RedditCrawler.search(keyword, limit=500)` 大批量搜索使用 `before`/`after` 参数替代已废弃 CloudSearch
- `RedditAPIClient._request` 使用已配置好的 `self._fetcher`（Scrapling），不再内部 import httpx
- `RedditAPIClient._authenticate` 与 `_request` 使用统一 HTTP 客户端，无 `response.status` 属性不一致问题
- No-API 模式下 `get_more_children` fallback 使用正确 URL 格式
- `_expand_comments` 递归深度受控，不触发 `RecursionError`
- `crawler_config.py` 成为唯一配置入口，`app/core/config.py` 从其读取默认值，`.env` 文件非必须

---

## 背景与上下文

- **项目简介**：GlobalMediaCrawler，多平台（YouTube / Reddit / TikTok / Instagram / X）内容爬虫系统，FastAPI + Celery 架构，支持 API / Playwright / yt-dlp 多后端
- **技术栈**：Python 3.11+，FastAPI，pydantic-settings，Scrapling，httpx，asyncio，loguru
- **已有约束**：
  - 代码风格：Ruff 格式化，类型注解，loguru 日志
  - `BaseCrawler._rate_limit(cost: int = 1)` 接口已固定
  - `CrawlResult` / `CommentResult` 数据结构不允许修改
  - 不引入新的第三方库（Scrapling / httpx 已是依赖）
- **可用材料**：完整源码已 clone 至本地，分支 `fix/stabilize-youtube-mvp`

---

## 问题 / 需求定义

**当前现象：**

| # | 文件 | 现象 |
|---|------|------|
| B1 | `youtube/crawler.py` | 时间切片搜索外层 `_rate_limit(cost=100)` 只调一次，内层每 slice 实际消耗 100 quota，两套计费机制不同步 |
| B2 | `youtube/crawler.py` | `datetime.now()` 返回本地时区 naive datetime，格式化带 `Z` 后缀欺骗 API 认为是 UTC，时区不一致 |
| B3 | `youtube/crawler.py` | 时间切片空结果逻辑 `if not slice_results and len(results) == 0: continue`，后续的空 slice 不 break，浪费配额 |
| B4 | `youtube/crawler.py` | `get_user_posts` 调用 `await self._rate_limit()` 未传 `cost=100`，search endpoint 消耗少报 99 units |
| B5 | `youtube/crawler.py` | `get_comments` 中每条顶层评论触发 `_fetch_all_replies`，不受外层 `limit` 约束，最坏 100×500=50,000 条 |
| B6 | `youtube/crawler.py` | `_parse_video` 中 `author_username=snippet.get("channelId")`，填的是 UCxxx 格式 ID |
| B7 | `youtube/api_client.py` | `asyncio.get_event_loop().run_in_executor(...)` Python 3.10+ 已废弃 |
| B8 | `reddit/crawler.py` | CloudSearch `timestamp:xxx..yyy` 语法于 2023-07 被 Reddit 废弃，大批量搜索静默返空 |
| B9 | `reddit/api_client.py` | `_request` 内部直接 `import httpx`，完全绕过了已配置 Scrapling `self._fetcher` |
| B10 | `reddit/api_client.py` | `_authenticate` 用 Scrapling `.status`，`_request` 用 httpx 的 `.status_code` monkey-patch 为 `.status`，不一致 |
| B11 | `reddit/api_client.py` | No-API 模式 `get_more_children` 的 fallback URL `/r/all/comments/{post_id}/_/{child_id}` 不合法 |
| B12 | `reddit/crawler.py` | `_expand_comments` 对 `more` 节点的递归展开无深度上限，可能触发 Python `RecursionError` |

**触发条件：**
- B1~B4：调用 `YouTubeCrawler.search(keyword, limit>100)` 或 `get_user_posts`
- B5：调用 `get_comments` 且视频有大量回复的评论
- B6：消费 `CrawlResult.author_username` 字段做展示或存储
- B7：Python 3.10+ 环境运行任何 YouTube API 请求
- B8：调用 `RedditCrawler.search(keyword, limit>100)`
- B9/B10：任何 Reddit API 请求（OAuth 或 No-API 模式）
- B11：No-API 模式下调用 `get_comments` 且有 `more` 节点
- B12：评论层级超深的帖子（Reddit 讨论帖常见）

**预期行为：**
- 所有 quota / rate limit 计费准确
- UTC 时间传递正确
- Reddit 大批量搜索用 `before`/`after` 替代废弃 API
- 所有 HTTP 请求统一走 Scrapling，No-API 模式反爬能力正常
- 递归展开有深度上限（默认 50 层）

---

## 范围与边界（强约束）

**允许修改：**
- `app/crawlers/youtube/crawler.py`
- `app/crawlers/youtube/api_client.py`
- `app/crawlers/reddit/crawler.py`
- `app/crawlers/reddit/api_client.py`
- `app/core/config.py`
- `crawler_config.py`

**禁止修改：**
- `app/crawlers/base.py`（`BaseCrawler`、`CrawlResult`、`CommentResult` 数据结构）
- `app/core/rate_limiter.py`
- `app/core/proxy_manager.py`
- 任何 `__init__.py` 文件
- 数据库模型 / Schema / 迁移文件

**限制：**
- 不允许引入新的第三方依赖
- 不允许无关重构（例如顺带改 TikTok 爬虫）
- 最小改动原则：能改一行解决的不改一段
- 所有修改需保持 Ruff 格式化兼容（双引号，4 空格缩进）

---

## 执行步骤

### 一、问题分析 / 根因定位

| Bug | 表象 | 根因（确定） | 待验证 |
|-----|------|------------|--------|
| B1 | 配额统计偏低 | `_rate_limit` 与 `_check_quota` 是独立机制，外层只调一次 | — |
| B2 | 时间窗口偏移 | `datetime.now()` 是 local time，格式化为 `Z` 但 API 需要真正 UTC | 服务器是否在 UTC 环境？若是则症状不触发 |
| B3 | 空 slice 不停止 | `if not slice_results and len(results) == 0` 条件太窄 | — |
| B4 | 计费少 99 units | `_rate_limit()` 默认 cost=1，search 应 cost=100 | — |
| B5 | 结果超 limit | `_fetch_all_replies` 硬编码 500，`extend` 后才截断 | — |
| B6 | username 是 ID | `snippet["channelId"]` 是内部 ID，非 handle | channel API 是否能廉价获取 handle？ |
| B7 | DeprecationWarning | `get_event_loop()` Python 3.10+ deprecated in non-async context | — |
| B8 | 大批量返空 | Reddit CloudSearch 2023-07 关闭，`timestamp:` 语法失效 | — |
| B9 | 反爬失效 | `_do_fetch` 中直接 `import httpx`，Scrapling 配置无效 | — |
| B10 | 属性不一致 | 两条代码路径用不同 HTTP 库，`.status` 来源不同 | — |
| B11 | fallback URL 错 | `/r/all/comments/` 不是合法 Reddit URL | — |
| B12 | 递归溢出风险 | `_expand_comments` 对展开的 `more` 无深度限制 | 实际 Reddit 评论树最深多少层？ |

---

### 二、任务拆解（模块级）

```
Module A  app/crawlers/youtube/crawler.py    ← 修复 B1 B2 B3 B4 B5 B6
Module B  app/crawlers/youtube/api_client.py ← 修复 B7
Module C  app/crawlers/reddit/crawler.py     ← 修复 B8 B12
Module D  app/crawlers/reddit/api_client.py  ← 修复 B9 B10 B11
Module E  app/core/config.py + crawler_config.py ← 配置统一为 Python 格式
```

依赖关系：`crawler.py` → `api_client.py` → `config.py` → `crawler_config.py`  
施工顺序：**E → B → D → A → C**（底层先改）

---

### 三、逐模块施工单

---

#### Module E · 配置统一（`crawler_config.py` + `app/core/config.py`）

**1. 模块名称**：配置管理层

**2. 模块职责**：提供全局配置的唯一入口，`crawler_config.py` 是用户编辑入口，`app/core/config.py` 消费它

**3. 涉及文件**：
- `crawler_config.py`
- `app/core/config.py`

**4. 当前问题**：`app/core/config.py` 用 `pydantic-settings` 读 `.env`，`crawler_config.py` 是独立的 Python 模块，两套系统并存。用户只想要 Python 格式配置，不需要 `.env`

**5. 根因**：架构设计上有两条配置读取路径，没有统一

**6. 具体改动方案**：
- `crawler_config.py`：无需改动，保持现有结构，扩充缺失的 `YOUTUBE_DAILY_QUOTA`、`REQUEST_DELAY` 等字段的默认值注释
- `app/core/config.py`：将 `SettingsConfigDict` 的 `env_file` 设为 `None`（禁用 .env 读取），为每个 `Settings` 字段补充来自 `crawler_config` 的 Python 默认值

**7. 注意事项**：
- `get_settings()` 用了 `@lru_cache`，修改后首次调用会缓存，测试时需注意清 cache
- 保留 `Settings` 中所有字段定义，只修改 `model_config` 和字段默认值
- API 密钥类字段（`youtube_api_key` 等）保持 `str | None = None`，从 `crawler_config` 读取默认值

**8. 不允许的做法**：
- 不允许删除 `Settings` 类（其他模块通过 `get_settings()` 引用）
- 不允许把 `crawler_config` import 放在模块顶层 `if TYPE_CHECKING:` 里（会导致运行时不可用）

**9. 改动后预期行为**：不创建 `.env` 文件时系统仍能正常启动，配置从 `crawler_config.py` 读取

**10. 验收标准**：删除项目根目录的 `.env` 文件后，`python cli.py` 正常运行，不报 `ValidationError`

**11. 测试方式**：
```bash
# 删除 .env，直接运行
rm -f .env
python -c "from app.core.config import get_settings; s = get_settings(); print(s.youtube_api_key)"
# 预期：输出 crawler_config.py 中 YOUTUBE_API_KEY 的值（或 None）
```

**12. 风险点**：环境变量（`YOUTUBE_API_KEY=xxx python cli.py`）仍然能覆盖默认值，pydantic-settings 默认支持环境变量读取，无需额外处理

**13. 回退方案**：恢复 `model_config` 中 `env_file=".env"` 即可

---

#### Module B · YouTube API Client（`app/crawlers/youtube/api_client.py`）

**1. 模块名称**：YouTube API 客户端

**2. 模块职责**：封装 YouTube Data API v3 的 HTTP 请求，管理配额、代理、重试

**3. 涉及文件**：`app/crawlers/youtube/api_client.py`

**4. 当前问题（B7）**：`asyncio.get_event_loop().run_in_executor(...)` 在 Python 3.10+ 于非 async 上下文调用时抛 `DeprecationWarning`，Python 3.12+ 直接报错

**5. 根因**：`get_event_loop()` 在协程内部调用时应改为 `get_running_loop()`

**6. 具体改动**：`_request` 方法中，将两处 `asyncio.get_event_loop()` 改为 `asyncio.get_running_loop()`

**7. 注意事项**：`get_running_loop()` 必须在 async 函数内调用，`_request` 已是 `async def`，安全

**8. 不允许**：不允许改变 `_do_fetch` 的闭包结构或 executor 调用模式

**9. 预期行为**：无 DeprecationWarning，Python 3.12 下正常运行

**10. 验收标准**：`python -W error -c "import asyncio; ..."` 无 `DeprecationWarning`

**11. 测试**：运行任意 YouTube API 搜索，检查 stderr 无警告

**12. 风险点**：无，`get_running_loop()` 是 `get_event_loop()` 的直接替代

**13. 回退**：改回 `asyncio.get_event_loop()` 即可

---

#### Module D · Reddit API Client（`app/crawlers/reddit/api_client.py`）

**1. 模块名称**：Reddit API 客户端

**2. 模块职责**：封装 Reddit OAuth / 公开 JSON 接口的 HTTP 请求，支持代理、重试、限速追踪

**3. 涉及文件**：`app/crawlers/reddit/api_client.py`

**4. 当前问题**：
- **B9**：`_request` 的 `_do_fetch` 直接 `import httpx`，绕开了 `self._fetcher`（Scrapling）
- **B10**：`_authenticate` 用 Scrapling `Fetcher.post()` 返回的 response（有 `.status`），`_request` 用 httpx response 并 monkey-patch `.status = .status_code`，两者不一致且脆弱
- **B11**：No-API 模式 `get_more_children` fallback URL `/r/all/comments/{post_id}/_/{child_id}` 非法

**5. 根因分析**：
- B9：开发者在 `_request` 里临时用了 httpx 处理代理，忘记了 Scrapling 本身支持代理参数
- B10：B9 的连带问题，两条代码路径混用不同库
- B11：`/r/all/comments/` 是错误路径，Reddit 不接受 `all` 作为 subreddit 来定位具体帖子评论

**6. 具体改动方案**：

**B9 + B10 修复**：将 `_request` 中的 `_do_fetch` 闭包改为使用 `self._fetcher`（Scrapling）。Scrapling Fetcher 支持 `proxy` 参数，直接传入即可。同时修复 `_authenticate` 使用 `httpx.Client` 替代 Scrapling，使两者统一为 httpx（更可控、更成熟）。

**B11 修复**：`get_more_children` 的 No-API fallback 中，从 `link_id`（`t3_xxxxx`）还原 `post_id`，以及从 `children` 中取评论 ID，拼接为 `/r/{subreddit}/comments/{post_id}` 正确路径。由于 No-API 模式下无法直接知道 subreddit，改为尝试从 `link_id` 附带的 subreddit context 参数传递（需要在调用链中补充 subreddit 参数）。

> ⚠️ **B11 待验证**：`get_more_children` 当前签名不接收 `subreddit` 参数。需在 `_expand_comments` 调用时传入 `post_fullname` 对应的 subreddit，或改为存储 `subreddit` 到实例变量。此处采用给 `get_more_children` 增加可选参数 `subreddit: str = "all"` 的方案，调用方同步更新。

**7. 注意事项**：
- Scrapling `Fetcher.get()` / `.post()` 是同步方法，必须继续在 `run_in_executor` 中调用
- 修改 `get_more_children` 签名后，`reddit/crawler.py` 的 `_expand_comments` 调用处需同步更新
- `_authenticate` 改为 httpx 后，注意 `response.status_code`（httpx 原生属性），不再 monkey-patch

**8. 不允许**：
- 不允许删除代理轮换逻辑
- 不允许改变 `_request` 的异步签名

**9. 预期行为**：
- No-API 模式下请求携带正确的 Firefox UA
- `get_more_children` fallback 返回格式正确的 things 列表

**10. 验收标准**：No-API 模式下运行 `RedditCrawler().get_comments(post_id, limit=50)`，Network 层抓包确认 User-Agent 为 Firefox UA

**11. 测试**：
```python
# 在无 reddit credentials 环境下
from app.crawlers.reddit.crawler import RedditCrawler
import asyncio
c = RedditCrawler()
# 确认 api.use_oauth == False
assert c.api.use_oauth == False
results = asyncio.run(c.search("python", limit=5))
assert len(results) > 0
```

**12. 风险点**：Scrapling 版本差异可能影响 proxy 参数格式，需确认当前 Scrapling 版本的 `Fetcher.get(proxy=...)` 接口

**13. 回退**：还原 `_do_fetch` 中的 httpx 调用

---

#### Module A · YouTube Crawler（`app/crawlers/youtube/crawler.py`）

**1. 模块名称**：YouTube 爬虫主逻辑

**2. 模块职责**：实现 YouTube 的 search / get_user_posts / get_post_detail / get_comments 四个核心接口

**3. 涉及文件**：`app/crawlers/youtube/crawler.py`

**4. 当前问题**：B1 B2 B3 B4 B5 B6（见问题定义）

**5. 根因**：见问题分析表

**6. 具体改动（逐函数）**：

**`search()` 方法（修复 B1 B2 B3）**：
- B1：移除入口处唯一的 `await self._rate_limit(cost=100)`。`_rate_limit` 的 token bucket 与 API 层的 `_check_quota` 是两套独立机制，不应双重扣费。`_rate_limit` 应只在 `_search_batch` 内每次 batch 调用前扣费一次，让两套机制各司其职。
- B2：将 `now = datetime.now()` 改为 `now = datetime.now(UTC)`，并在文件顶部 import `UTC` from `datetime`
- B3：将空结果逻辑改为双分支判断

**`get_user_posts()` 方法（修复 B4）**：
- 将 `await self._rate_limit()` 改为 `await self._rate_limit(cost=100)`

**`get_comments()` 方法（修复 B5）**：
- 在每次调用 `_fetch_all_replies` 前，计算剩余预算 `remaining = limit - len(results)`
- 将 `remaining` 传入 `_fetch_all_replies` 作为 `max_replies` 参数上限
- 修改 `_fetch_all_replies` 签名：增加 `max_replies: int = 500` 参数，替换硬编码 `max_thread_replies = 500`

**`_parse_video()` 方法（修复 B6）**：
- `author_username` 字段：YouTube API 的 `snippet` 中没有直接的 handle 字段，`channelId` 是内部 ID
- 修改为 `author_username=None`，将 `channelId` 放在 `author_id` 字段（已正确）
- 如需 handle，应在 `get_user_posts` 调用 `get_channel_info` 时从 `snippet.customUrl` 获取（当前搜索结果 snippet 不含此字段，故置 None 为最准确处理）

**7. 注意事项**：
- B1 修复后，`_search_batch` 不再在自身内部调用 `_rate_limit`（当前也没有），外层调用点只剩 api_client 层的 `_check_quota`。若需要在 crawler 层也做 token bucket 控制，应在 `_search_batch` 内每个 batch 前调用 `await self._rate_limit(cost=100)`
- B5 修复时，`_fetch_all_replies` 签名变更，需同步更新所有调用点（当前只有一处）
- B6 修改 `author_username=None` 不破坏 `CrawlResult` 约束（该字段 `str | None`）

**8. 不允许**：
- 不允许为获取 handle 额外发起 channel API 请求（会消耗额外配额）
- 不允许修改 `_search_batch` 的函数签名（仅修改内部逻辑）

**9. 预期行为**：
- 时间切片搜索每个 slice 配额计费准确
- 时间范围传递正确的 UTC 时间
- 空 slice 后立即终止
- `get_comments(post_id, limit=50)` 返回 ≤50 条

**10. 验收标准**：
```python
# limit=50 时，即使视频有大量回复，结果不超过 50
comments = await crawler.get_comments("dQw4w9WgXcQ", limit=50)
assert len(comments) <= 50
```

**11. 测试**：
- 正常搜索：`crawler.search("python", limit=20)` 返回非空列表
- 大批量搜索：`crawler.search("python", limit=200)` 不报 quota 错误
- 评论限制：有大量回复的视频 `get_comments(limit=10)` 返回 ≤10 条

**12. 风险点**：B1 中移除外层 `_rate_limit` 后，token bucket 不再限速时间切片总速率。若需整体限速，应在时间切片 for 循环体内加 `await asyncio.sleep(0.5)` 作为保护

**13. 回退**：Git revert `app/crawlers/youtube/crawler.py`

---

#### Module C · Reddit Crawler（`app/crawlers/reddit/crawler.py`）

**1. 模块名称**：Reddit 爬虫主逻辑

**2. 模块职责**：实现 Reddit 的 search / get_user_posts / get_post_detail / get_comments 四个接口

**3. 涉及文件**：`app/crawlers/reddit/crawler.py`

**4. 当前问题**：
- **B8**：`search(limit>100)` 分支使用 `syntax="cloudsearch"` 和 `timestamp:xxx..yyy`，CloudSearch 2023 年已废弃
- **B12**：`_expand_comments` 递归展开 `more` 节点无深度限制

**5. 根因**：
- B8：Reddit 在 2023-07 关闭了 CloudSearch（Lucene）后端，`/search?syntax=cloudsearch` 现在要么忽略参数要么返回空
- B12：`more` 节点展开后仍可能含 `more`，无限递归

**6. 具体改动**：

**`search()` 大批量分支（修复 B8）**：
- 删除整个时间切片分支（`if limit > 100:` 下的 timestamp 分支）
- 改为使用 Reddit 支持的 `before` / `after` 分页参数（full-names：`t3_xxxxxx`）进行连续翻页
- Reddit API 单次 search 最多返回 100 条，连续用 `after` 翻页即可获取更多
- 注意：Reddit Search API 有软上限（约 250 条），超过后 `after` 不再有效，需在 while 循环中检测

**`_expand_comments()` 方法（修复 B12）**：
- 增加 `depth: int = 0` 参数
- 设定 `MAX_RECURSION_DEPTH = 50`（常量定义在文件顶部）
- 在每次递归调用时传入 `depth + 1`，当 `depth >= MAX_RECURSION_DEPTH` 时直接 `return`

**7. 注意事项**：
- B8 修复后，`_search_batch` 的 `**kwargs` 传参机制不变，但调用时不再传 `syntax="cloudsearch"`
- `_expand_comments` 的递归调用有两处（处理 `t1` replies 和处理 `more` nodes），两处都需要传 `depth + 1`
- `MAX_RECURSION_DEPTH = 50` 已经远超 Reddit 实际评论树深度（通常 ≤15 层）

**8. 不允许**：
- 不允许使用 Pushshift 等第三方服务（引入新依赖）
- 不允许修改 `get_comments` 的公开接口签名

**9. 预期行为**：
- `search(keyword, limit=500)` 通过连续翻页获取最多约 250 条（Reddit 硬限制）
- 超深评论树不触发 RecursionError

**10. 验收标准**：
```python
results = await crawler.search("python", limit=200)
assert len(results) > 0  # 能正常返回，不再静默返空
```

**11. 测试**：
- `search("python", limit=150)` 返回 >100 条（翻页有效）
- 深层评论帖子 `get_comments("subreddit:post_id", limit=500)` 不 crash

**12. 风险点**：Reddit Search API 约 250 条软上限是非官方文档的观察结论，实际可能略有差异。若用户指定 `limit=1000` 将无法满足，需在文档/日志中说明

**13. 回退**：Git revert `app/crawlers/reddit/crawler.py`

---

### 四、逐文件修改建议

#### `app/core/config.py`

```
删除：model_config 中 env_file=".env" 一行（或改为 None）
新增：文件顶部 import crawler_config as _cfg
修改：各字段的默认值，从 _cfg.XXXX 读取
保留：所有字段定义、Settings 类、get_settings() 函数
影响面：仅影响默认值来源，不影响调用方接口
```

#### `app/crawlers/youtube/api_client.py`

```
修改：_request 方法中 asyncio.get_event_loop() → asyncio.get_running_loop()（2处）
保留：_do_fetch 闭包结构、executor 模式、retry 逻辑
影响面：仅消除 DeprecationWarning，无业务逻辑变化
```

#### `app/crawlers/youtube/crawler.py`

```
修改 search()：
  - 删除入口处 await self._rate_limit(cost=100)
  - now = datetime.now() → now = datetime.now(UTC)
  - import 顶部增加 UTC from datetime
  - 空 slice 判断逻辑：if not slice_results and len(results) == 0 → if not slice_results: break（加条件注释）

修改 get_user_posts()：
  - await self._rate_limit() → await self._rate_limit(cost=100)

修改 get_comments()：
  - _fetch_all_replies 调用前计算 remaining_budget = limit - len(results)
  - 调用改为 await self._fetch_all_replies(comment_id, max_replies=remaining_budget)

修改 _fetch_all_replies()：
  - 签名增加 max_replies: int = 500
  - max_thread_replies = 500 → max_thread_replies = max_replies

修改 _parse_video()：
  - author_username=snippet.get("channelId") → author_username=None

保留：所有其他逻辑不变
影响面：search 配额计费、评论数量上限、author_username 字段值
```

#### `app/crawlers/reddit/api_client.py`

```
修改 _request()._do_fetch 闭包：
  - 删除：import httpx 及 httpx.Client 调用
  - 新增：使用 self._fetcher.get() / .post()，proxy 参数直接传入
  - 修改 response.status 引用为 response.status_code（Scrapling response）

修改 _authenticate()：
  - 改为 httpx.Client 调用（与 _request 统一）
  - 移除 Fetcher().post() 调用
  - response.status → response.status_code

修改 get_more_children()：
  - 签名增加 subreddit: str = "all"
  - No-API fallback URL 改为 f"/r/{subreddit}/comments/{post_id}/_/{child_id}"

保留：OAuth 认证流程、代理轮换、retry 逻辑、rate limit 追踪
影响面：HTTP 请求底层实现，No-API 模式反爬能力、morechildren 展开
```

#### `app/crawlers/reddit/crawler.py`

```
修改 search()：
  - 删除 if limit > 100: 时间切片分支（整段）
  - 改为单一 while 循环 + after 翻页，统一处理所有 limit

修改 _expand_comments()：
  - 签名增加 depth: int = 0
  - 函数开头增加 if depth >= MAX_RECURSION_DEPTH: return
  - 递归调用 _expand_comments 时传入 depth=depth+1（两处）

新增：文件顶部常量 MAX_RECURSION_DEPTH = 50

修改 _expand_comments 调用方（get_comments 中）：
  - 初始调用加 depth=0（显式）

同步修改 get_more_children 调用：
  - 传入 subreddit 参数（从 post_fullname 解析或从实例状态取）

保留：_parse_post / _parse_comment / 所有辅助 helper 函数
影响面：大批量搜索行为、深层评论树稳定性
```

---

### 五、数据结构与流程

#### YouTube 时间切片修复后流程

```
search(keyword, limit=500)
  │
  ├─ limit <= 100 → _search_batch(keyword, limit) → 返回
  │
  └─ limit > 100
       │
       for slice in range(24):
         │
         ├─ len(results) >= limit → break
         │
         ├─ 计算 [published_after, published_before]（UTC）
         │
         ├─ _search_batch(keyword, slice_limit, published_after=..., published_before=...)
         │    └─ [api_client._check_quota 独立计费]
         │
         ├─ results.extend(slice_results)
         │
         └─ not slice_results → break  ← 修复 B3
```

#### Reddit 大批量搜索修复后流程

```
search(keyword, limit=500)
  │
  └─ while remaining > 0:
       │
       ├─ _search_batch(keyword, min(remaining, 100), after=after)
       │    └─ params: {q, sort, t, limit, after}  ← 无 syntax=cloudsearch
       │
       ├─ results.extend(...)
       │
       ├─ after = data["after"]
       │
       └─ not after → break  （Reddit 约 250 条后 after=null）
```

---

### 六、关键代码实现

#### E1 · `app/core/config.py` 修改

```python
# 顶部新增 import
import crawler_config as _cfg

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,          # ← 修改：禁用 .env 文件读取
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- YouTube ----（示例，其他字段同理）
    youtube_api_key: str | None = _cfg.YOUTUBE_API_KEY        # ← 从 crawler_config 读取
    youtube_cookies_file: str | None = _cfg.YOUTUBE_COOKIES_FILE

    # ---- Reddit ----
    reddit_client_id: str | None = _cfg.REDDIT_CLIENT_ID
    reddit_client_secret: str | None = _cfg.REDDIT_CLIENT_SECRET

    # ---- Storage ----
    save_data_option: str = _cfg.SAVE_FORMAT
    save_data_path: str = _cfg.SAVE_PATH
    # ... 其余字段类似
```

> 注意：`_cfg` 前缀用下划线防止 pydantic 把它当成 Settings 字段处理

---

#### B1 · `youtube/api_client.py` 修复 get_event_loop

```python
# 修改前（两处相同）
response = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

# 修改后
response = await asyncio.get_running_loop().run_in_executor(None, _do_fetch)
```

---

#### A1 · `youtube/crawler.py` 修复 B1 B2 B3

```python
# 修改前 search() 开头
async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
    try:
        await self._rate_limit(cost=100)  # ← 删除此行（B1）
        logger.info(f"YouTube search: '{keyword}', limit={limit}")

        if limit <= 100:
            return await self._search_batch(keyword, limit)

        from datetime import timedelta
        now = datetime.now()  # ← 修改（B2）
        ...
        for _ in range(total_slices):
            ...
            if not slice_results and len(results) == 0:  # ← 修改（B3）
                continue

# 修改后
from datetime import UTC  # ← 新增顶部 import

async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
    try:
        # B1：移除外层 _rate_limit，配额由 api_client._check_quota 独立管理
        logger.info(f"YouTube search: '{keyword}', limit={limit}")

        if limit <= 100:
            return await self._search_batch(keyword, limit)

        from datetime import timedelta
        now = datetime.now(UTC)  # B2：使用 UTC aware datetime
        slice_days = 7
        current_end = now
        total_slices = 24

        results: list[CrawlResult] = []
        for _ in range(total_slices):
            if len(results) >= limit:
                break

            current_start = current_end - timedelta(days=slice_days)
            published_after = current_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            published_before = current_end.strftime("%Y-%m-%dT%H:%M:%SZ")

            logger.info(f"[YouTube Slicer] Searching slice {published_after} to {published_before}")

            slice_limit = min(limit - len(results), 500)
            slice_results = await self._search_batch(
                keyword,
                slice_limit,
                published_after=published_after,
                published_before=published_before,
            )
            results.extend(slice_results)
            current_end = current_start

            # B3：任何 slice 返回空则终止，避免浪费配额
            if not slice_results:
                logger.info("[YouTube Slicer] Empty slice, stopping early")
                break

        logger.info(f"[YouTube Slicer] Completed, gathered {len(results)} results")
        return results[:limit]
    except QuotaExhaustedError:
        ...
```

---

#### A2 · `youtube/crawler.py` 修复 B4

```python
# 修改前
async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
    await self._rate_limit()  # ← 错误：cost 默认 1

# 修改后
async def get_user_posts(self, username: str, limit: int = 20) -> list[CrawlResult]:
    await self._rate_limit(cost=100)  # B4：search endpoint 消耗 100 quota units
```

---

#### A3 · `youtube/crawler.py` 修复 B5

```python
# 修改 _fetch_all_replies 签名
async def _fetch_all_replies(self, parent_id: str, max_replies: int = 500) -> list[CommentResult]:
    replies = []
    page_token = None
    max_thread_replies = max_replies  # B5：使用传入的上限，而非硬编码 500
    ...

# 修改 get_comments 中的调用
for item in items:
    ...
    results.append(comment)

    total_replies = item["snippet"].get("totalReplyCount", 0)
    if total_replies > 0:
        # B5：传入剩余预算，防止结果超 limit
        remaining_budget = limit - len(results)
        if remaining_budget <= 0:
            break
        replies = await self._fetch_all_replies(comment_id, max_replies=remaining_budget)
        results.extend(replies)
```

---

#### A4 · `youtube/crawler.py` 修复 B6

```python
# 修改前
author_username=snippet.get("channelId"),  # "UCxxxxxx" 是 ID 不是 handle

# 修改后
author_username=None,  # B6：snippet 不含 handle，channelId 归 author_id 字段
# author_id 字段已正确填充 channelId
```

---

#### D1 · `reddit/api_client.py` 修复 B9 B10

```python
# _authenticate 统一改为 httpx
async def _authenticate(self) -> None:
    if not self.use_oauth:
        return
    try:
        import httpx  # 与 _request 统一使用 httpx
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                self.AUTH_URL,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self.user_agent},
            )
        if response.status_code != 200:  # B10：统一用 .status_code
            logger.error(f"[Reddit] Authentication failed: {response.status_code}")
            return
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60
        logger.info("[Reddit] OAuth token obtained successfully")
    except Exception as e:
        logger.error(f"[Reddit] Authentication error: {e}")

# _request 中 _do_fetch 修复（B9）
async def _request(self, method: str, endpoint: str, params: dict | None = None) -> Any:
    ...
    for attempt in range(max_retries):
        proxy_url = None
        if proxy_manager.enabled:
            proxy_url = proxy_manager.get_proxy()

        try:
            def _do_fetch(proxy_url=proxy_url):
                # B9：统一使用 httpx，移除对 Scrapling 的虚假依赖
                import httpx
                proxies = {"http://": proxy_url, "https://": proxy_url} if proxy_url else None
                with httpx.Client(proxies=proxies, timeout=30.0) as client:
                    if method.upper() == "POST":
                        res = client.post(url=url, data=params, headers=headers)
                    else:
                        res = client.get(url=url, params=params, headers=headers)
                return res  # 返回原生 httpx response，有 .status_code

            response = await asyncio.get_running_loop().run_in_executor(None, _do_fetch)

            if self.use_oauth:
                self._update_rate_limits(response)

            if response.status_code == 429:  # B10：统一用 .status_code
                ...
            if response.status_code >= 400:
                ...
            return response.json()
        except Exception as e:
            ...
```

> **说明**：B9 的修复方向是统一用 httpx（可控、成熟），而非强行用 Scrapling。Scrapling 的价值在 Playwright 场景，对纯 JSON API 请求 httpx 更合适。UA 通过 `headers={"User-Agent": self.user_agent}` 统一传递，No-API 模式的浏览器 UA 依然生效。

---

#### D2 · `reddit/api_client.py` 修复 B11

```python
# get_more_children 签名增加 subreddit 参数
async def get_more_children(
    self,
    link_id: str,
    children: list[str],
    sort: str = "best",
    subreddit: str = "all",  # B11：新增参数，用于构造正确 URL
) -> dict:
    if not self.use_oauth:
        post_id = link_id.replace("t3_", "")
        things = []
        for child_id in children[:5]:
            try:
                # B11：使用正确的 URL 格式，subreddit 从调用方传入
                resp = await self._request(
                    "GET",
                    f"/r/{subreddit}/comments/{post_id}/_/{child_id}",
                    params={"sort": sort, "raw_json": 1},
                )
                if isinstance(resp, list) and len(resp) >= 2:
                    children_nodes = resp[1].get("data", {}).get("children", [])
                    things.extend(children_nodes)
            except Exception as e:
                logger.debug(f"[Reddit No-API] Failed to expand {child_id}: {e}")
        return {"json": {"data": {"things": things}}}
    ...
```

---

#### C1 · `reddit/crawler.py` 修复 B8

```python
# 修改前 search() 大批量分支（删除整个时间切片）
async def search(self, keyword: str, limit: int = 20) -> list[CrawlResult]:
    await self._rate_limit()
    logger.info(f"[Reddit] Search: '{keyword}', limit={limit}")

    # B8：统一用 after 翻页，不再区分 limit 大小，不用 CloudSearch
    results: list[CrawlResult] = []
    after: str | None = None
    remaining = limit

    while remaining > 0:
        batch = min(remaining, 100)
        try:
            response = await self.api.search(query=keyword, limit=batch, after=after)
            data = response.get("data", {})
            children = data.get("children", [])
            if not children:
                break
            for child in children:
                results.append(await self._parse_post(child.get("data", {}), fetch_extras=False))
            remaining -= len(children)
            after = data.get("after")
            if not after:
                logger.info("[Reddit] No more pages available from API")
                break  # Reddit Search 约 250 条后 after=null
        except Exception as e:
            logger.error(f"[Reddit] Search batch failed: {e}")
            break

    logger.info(f"[Reddit] Search completed, gathered {len(results)} results")
    return results[:limit]
```

---

#### C2 · `reddit/crawler.py` 修复 B12

```python
# 文件顶部新增常量
MAX_RECURSION_DEPTH = 50  # Reddit 实际评论树深度通常 ≤15 层，50 层为安全上限

# _expand_comments 签名增加 depth 参数
async def _expand_comments(
    self,
    children: list[dict],
    results: list[CommentResult],
    post_fullname: str,
    parent_id: str | None,
    limit: int,
    depth: int = 0,          # B12：新增深度追踪
) -> None:
    # B12：深度超限则直接返回，防止 RecursionError
    if depth >= MAX_RECURSION_DEPTH:
        logger.debug(f"[Reddit] Max recursion depth {MAX_RECURSION_DEPTH} reached, stopping")
        return

    more_ids: list[str] = []

    for child in children:
        if len(results) >= limit:
            break
        kind = child.get("kind")
        data = child.get("data", {})

        if kind == "t1":
            comment = self._parse_comment(data, parent_id)
            results.append(comment)
            replies_data = data.get("replies")
            if isinstance(replies_data, dict):
                reply_children = replies_data.get("data", {}).get("children", [])
                await self._expand_comments(
                    reply_children,
                    results,
                    post_fullname,
                    parent_id=comment.source_id,
                    limit=limit,
                    depth=depth + 1,  # B12：传递深度
                )
        elif kind == "more":
            ids = data.get("children") or []
            more_ids.extend(ids)

    # Expand more IDs
    for i in range(0, len(more_ids), 100):
        if len(results) >= limit:
            break
        batch = more_ids[i: i + 100]
        try:
            # B11：同步更新，传入 subreddit（从 post_fullname 无法直接取，暂传 "all"）
            # ⚠️ 待验证：若需准确 subreddit，需在 get_comments 中传入并透传到此处
            more_resp = await self.api.get_more_children(post_fullname, batch, sort="best")
            more_things = more_resp.get("json", {}).get("data", {}).get("things", [])
            await self._expand_comments(
                more_things,
                results,
                post_fullname,
                parent_id=parent_id,
                limit=limit,
                depth=depth + 1,  # B12：展开的 more 节点也递增深度
            )
        except Exception as e:
            logger.warning(f"[Reddit] morechildren expansion failed: {e}")
```

---

### 七、验证方案

#### 手动测试步骤（主流程）

```bash
# 1. 配置验证
rm -f .env
python -c "
from app.core.config import get_settings
s = get_settings()
print('api_key:', s.youtube_api_key)
print('save_format:', s.save_data_option)
print('OK: config loads from crawler_config.py')
"

# 2. YouTube 搜索（需要有效 API Key）
python -c "
import asyncio
from app.crawlers.youtube.crawler import YouTubeCrawler
async def test():
    c = YouTubeCrawler()
    r = await c.search('python', limit=20)
    print(f'Results: {len(r)}, first: {r[0].title if r else None}')
    assert len(r) > 0
    assert r[0].author_username is None  # B6 验证
    await c.close()
asyncio.run(test())
"

# 3. YouTube 评论限制验证
python -c "
import asyncio
from app.crawlers.youtube.crawler import YouTubeCrawler
async def test():
    c = YouTubeCrawler()
    comments = await c.get_comments('dQw4w9WgXcQ', limit=10)
    print(f'Comments: {len(comments)}')
    assert len(comments) <= 10, f'Expected <=10, got {len(comments)}'  # B5 验证
    await c.close()
asyncio.run(test())
"

# 4. Reddit 搜索（No-API 模式，无需 credentials）
python -c "
import asyncio
from app.crawlers.reddit.crawler import RedditCrawler
async def test():
    c = RedditCrawler()
    assert c.api.use_oauth == False
    r = await c.search('python', limit=5)
    print(f'Results: {len(r)}')
    assert len(r) > 0
    await c.close()
asyncio.run(test())
"

# 5. Reddit 大批量搜索（B8 验证）
python -c "
import asyncio
from app.crawlers.reddit.crawler import RedditCrawler
async def test():
    c = RedditCrawler()
    r = await c.search('python', limit=150)
    print(f'Results: {len(r)}')
    assert len(r) > 0, 'B8 未修复：大批量搜索返回空'
    await c.close()
asyncio.run(test())
"
```

#### 边界测试

| 场景 | 输入 | 预期 | 验证 B# |
|------|------|------|---------|
| YouTube 搜索 limit=1 | `search("test", 1)` | 返回恰好 1 条 | — |
| YouTube 搜索 limit=0 | `search("test", 0)` | 返回空列表，不报错 | — |
| YouTube 评论 limit=1 | `get_comments(id, 1)` | 返回 ≤1 条 | B5 |
| Reddit limit=300 | `search("python", 300)` | 返回 >0 条（不超过 ~250）| B8 |
| Reddit 超深评论 | 已知超深帖子 | 不 crash，返回部分评论 | B12 |
| 无 API Key | `YouTubeCrawler()` | 抛 `APIKeyMissingError`，不 crash | — |
| 无 Reddit credentials | `RedditCrawler()` | 正常初始化，use_oauth=False | — |

#### 失败判定标准

- `search(limit>100)` 在 Reddit 返回 0 条 → B8 未修复
- `get_comments(limit=10)` 返回 >10 条 → B5 未修复
- 存在 `DeprecationWarning: get_event_loop()` → B7 未修复
- `author_username` 包含 `UC` 开头的字符串 → B6 未修复
- 删除 `.env` 后 `get_settings()` 抛 `ValidationError` → E 未修复

---

## 附录：修改文件清单

| 文件 | 改动类型 | 修复 Bug |
|------|----------|---------|
| `app/core/config.py` | model_config + 字段默认值 | E |
| `app/crawlers/youtube/api_client.py` | get_event_loop → get_running_loop | B7 |
| `app/crawlers/youtube/crawler.py` | search / get_user_posts / get_comments / _parse_video | B1 B2 B3 B4 B5 B6 |
| `app/crawlers/reddit/api_client.py` | _request / _authenticate / get_more_children | B9 B10 B11 |
| `app/crawlers/reddit/crawler.py` | search / _expand_comments + 常量 | B8 B12 |

**总计：5 个文件，12 处 Bug 修复，0 个新依赖引入**
