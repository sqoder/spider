# ============================================================
#   GlobalMediaCrawler — 多平台总配置文件
#   修改此文件控制所有平台的爬取行为。
#
#   使用方法：
#       python run.py
# ============================================================


# ============================================================
# 一、总开关：启用哪些平台（注释掉某行即关闭该平台）
# ============================================================
ENABLED_PLATFORMS = [
    # "reddit",
    # "youtube",
    # "tiktok",
    "instagram",
    # "x",
]


# ============================================================
# 二、YouTube 配置
# ============================================================
YOUTUBE = {
    # 抓取模式: "keyword" | "url" | "user"
    "mode": "keyword",

    # keyword 模式 ——————————————————————————
    "keyword": "内马尔",
    "search_limit": 5,          # 搜索结果数量

    # url 模式 ————————————————————————————
    "urls": [
        # "https://www.youtube.com/watch?v=xxxxxxxxxxx",
    ],

    # user 模式 ———————————————————————————
    "user_handle": "MrBeast",   # 频道名（不带 @）
    "user_post_limit": 5,

    # 评论配置 ————————————————————————————
    "comments_enabled": True,
    "comments_count": 100,
    "include_replies": True,    # True=抓一二级评论，False=仅一级

    # 媒体下载 ————————————————————————————
    "media_enabled": True,
    "media_quality": 360,       # 360 | 720 | 1080
}


# ============================================================
# 三、Reddit 配置
# ============================================================
REDDIT = {
    # 抓取模式: "keyword" | "url" | "user"
    "mode": "keyword",

    "keyword": "马斯克",
    "search_limit": 20,

    "urls": [
        # "https://www.reddit.com/r/technology/comments/xxxxxx/",
    ],

    "user_handle": "spez",
    "user_post_limit": 10,

    "comments_enabled": True,
    "comments_count": 50,
    "include_replies": True,

    "media_enabled": True,      # 开启 Reddit 图片与图集媒体自动下载
}


# ============================================================
# 四、TikTok 配置
# ============================================================
TIKTOK = {
    # 抓取模式: "keyword" | "url" | "user"
    # 注意: TikTok search 走 hashtag（关键词不含空格）目前无API时不可用，请使用 user 模式或 url 模式
    "mode": "keyword",

    "keyword": "马斯克",
    "search_limit": 2,

    "urls": [
        # "https://www.tiktok.com/@username/video/xxxxxxxxxxxxxxxxxx",
    ],

    "user_handle": "charlidamelio",
    "user_post_limit": 5,

    "comments_enabled": True,  # 开启评论测试
    "comments_count": 50,
    "include_replies": False,

    "media_enabled": True,
}


# ============================================================
# 五、Instagram 配置
# ============================================================
INSTAGRAM = {
    # 抓取模式: "keyword" | "url" | "user"
    # 注意: Instagram search 走 hashtag
    "mode": "url",

    "keyword": "travel",
    "search_limit": 10,

    "urls": [
        "https://www.instagram.com/p/DXHKcyvEWfr/",
    ],

    "user_handle": "natgeo",
    "user_post_limit": 3,

    "comments_enabled": False,  # Instagram 评论暂不支持
    "comments_count": 50,
    "include_replies": False,

    "media_enabled": True,
}


# ============================================================
# 六、X (Twitter) 配置
# ============================================================
X = {
    # 抓取模式: "keyword" | "url" | "user"
    # 注意: X 的 keyword 模式需要配置 twscrape 账号；user 和 url 模式免登录！
    "mode": "user",

    "keyword": "AI news",
    "search_limit": 10,

    "urls": [
        # "https://x.com/username/status/xxxxxxxxxxxxxxxxxx",
    ],

    "user_handle": "elonmusk",
    "user_post_limit": 3,

    "comments_enabled": False,  # X 评论暂不支持
    "comments_count": 50,
    "include_replies": False,

    "media_enabled": True,
}
