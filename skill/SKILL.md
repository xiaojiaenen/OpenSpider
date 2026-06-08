---
name: openspider
description: |
  通过 OpenSpider 平台编写和管理爬虫。当用户想要从网站抓取数据、编写爬虫、自动化数据采集时使用此 Skill。即使用户只是说"帮我抓取 X"、"我需要从这个网站获取数据"，也应使用此 Skill。
---

# OpenSpider 爬虫编写指南

所有爬虫继承 `BaseSpider`，实现 `run()` 方法，yield 数据字典。

## 最简示例

```python
from openspider.spiders.base import BaseSpider

class MySpider(BaseSpider):
    name = "my_spider"
    description = "抓取示例网站"
    start_urls = ["https://example.com"]

    async def run(self):
        page = await self.get(self.start_urls[0])
        for item in page.css(".article"):
            if self.should_stop:
                break
            yield {
                "title": item.css("h2::text").get(""),
                "link": item.css("a::attr(href)").get(""),
            }
```

## 请求方法

```python
page = await self.get(url)           # GET 请求
page = await self.post(url, data={}) # POST 请求
page = await self.fetch(url)         # 同 get()
```

返回 Scrapling Response 对象，支持 CSS/XPath 选择器：
```python
page.css("div.title::text").get("")         # 单个文本
page.css("a::attr(href)").getall()          # 所有链接
page.xpath("//h1/text()").get("")           # XPath
page.css("div.item", adaptive=True)         # 自适应选择器
```

## 高级模式：parse() 回调

适合多级页面（列表→详情、自动翻页）：

```python
class BlogSpider(BaseSpider):
    name = "blog"
    start_urls = ["https://blog.example.com"]

    async def parse(self, response):
        for link in response.css("a.post-link::attr(href)").getall():
            yield self.follow(link, callback=self.parse_detail)

    async def parse_detail(self, response):
        yield {
            "title": response.css("h1::text").get(""),
            "content": response.css("article").get(""),
        }
```

## 并发请求

```python
urls = ["https://example.com/page/1", "https://example.com/page/2"]
async for resp in self.concurrent_fetch(urls, max_concurrent=5):
    yield {"url": resp.url, "title": resp.css("h1::text").get("")}
```

## 字段定义（自动建表）

定义 `fields` 后，平台自动创建数据库表存储数据：

```python
class ProductSpider(BaseSpider):
    name = "products"
    fields = [
        {"name": "title", "type": "VARCHAR(512)"},
        {"name": "price", "type": "VARCHAR(64)"},
        {"name": "url", "type": "VARCHAR(2048)"},
    ]
    dedup_key = ["url"]  # 去重键，相同 url 不重复插入
```

## 常用配置

```python
class MySpider(BaseSpider):
    name = "my_spider"
    start_urls = ["https://example.com"]

    # 请求控制
    concurrent_requests = 4        # 并发数
    download_delay = 0.5           # 请求间隔（秒）
    timeout = 30                   # 超时秒数
    max_retries = 3                # 重试次数

    # 反爬
    impersonate = "chrome"         # TLS 指纹伪装
    proxies = ["http://proxy:8080"]  # 代理
    block_ads = True               # 屏蔽广告域名

    # 浏览器模式（use_stealth=True 时生效）
    use_stealth = True             # 启用隐身浏览器
    solve_cloudflare = True        # 自动破解 Cloudflare
    wait_selector = ".content"     # 等待元素出现
    wait = 2000                    # 额外等待毫秒
    capture_xhr = r"/api/data"     # 拦截 XHR 请求

    # 数据
    crawl_mode = "incremental"     # incremental（增量）| full（全量，清空表再跑）
```

## 页面交互（浏览器模式）

```python
async def run(self):
    async def scroll_page(page):
        await page.mouse.wheel(0, 1000)
        await page.wait_for_timeout(2000)

    page = await self.get("https://example.com", page_action=scroll_page)
    yield {"data": page.css(".item").getall()}
```

## XHR 拦截（SPA 应用）

```python
class SpaSpider(BaseSpider):
    name = "spa_demo"
    use_stealth = True
    capture_xhr = r"/api/items"

    async def run(self):
        page = await self.get("https://spa-site.com")
        for xhr in page.captured_xhr:
            data = xhr.json()
            yield data
```

## 生命周期钩子

```python
async def on_start(self):
    """爬虫启动前"""
    pass

async def on_complete(self):
    """爬虫完成后"""
    pass

async def on_error(self, error: Exception):
    """出错时"""
    pass

async def on_item_scraped(self, item: dict) -> dict | None:
    """每条数据后处理，返回 None 则丢弃"""
    return item
```

## 模板爬虫

### RuleSpider（规则驱动）

自动跟进链接，声明式规则：

```python
from openspider.spiders.templates import RuleSpider

class BlogCrawler(RuleSpider):
    name = "blog"
    start_urls = ["https://blog.example.com"]

    def rules(self):
        from scrapling.spiders import CrawlRule, LinkExtractor
        return [
            CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
        ]

    async def parse_post(self, response):
        yield {"title": response.css("h1::text").get("")}
```

### SitemapRuleSpider（Sitemap 驱动）

```python
from openspider.spiders.templates import SitemapRuleSpider

class ProductCrawler(SitemapRuleSpider):
    name = "products"
    sitemap_urls = ["https://shop.example.com/sitemap.xml"]

    def rules(self):
        from scrapling.spiders import CrawlRule, LinkExtractor
        return [
            CrawlRule(LinkExtractor(allow=r"/products/"), callback=self.parse_product),
        ]

    async def parse_product(self, response):
        yield {"name": response.css("h1::text").get(""), "price": response.css(".price::text").get("")}
```

## 数据存储与管道（Sinks）

### 默认行为

不配置 `sinks` 时，只要定义了 `fields`，数据自动写入数据库（平台自动建表）。这是最常用的方式，不需要额外配置。

```python
class ProductSpider(BaseSpider):
    name = "products"
    fields = [
        {"name": "title", "type": "VARCHAR(512)"},
        {"name": "price", "type": "VARCHAR(64)"},
        {"name": "url", "type": "VARCHAR(2048)"},
    ]
    dedup_key = ["url"]  # 可选：相同 url 不重复插入（upsert）

    async def run(self):
        page = await self.get("https://shop.com/products")
        for item in page.css(".product"):
            yield {
                "title": item.css("h2::text").get(""),
                "price": item.css(".price::text").get(""),
                "url": item.css("a::attr(href)").get(""),
            }
```

### 自定义 Sink

配置 `sinks` 后，数据只写入指定的 sinks，不再写默认数据库：

```python
class ExportSpider(BaseSpider):
    name = "export_demo"
    sinks = [
        {"type": "csv", "path": "./output/data.csv"},
        {"type": "json", "path": "./output/data.jsonl"},
    ]

    async def run(self):
        yield {"name": "test", "value": 123}
```

### 可用 Sink 类型

| type | 说明 | 必填参数 |
|------|------|----------|
| `csv` | CSV 文件 | `path` |
| `json` | JSON/JSONL 文件 | `path` |
| `excel` | Excel 文件 | `path` |
| `parquet` | Parquet 列式文件 | `path` |
| `kafka` | Apache Kafka | `topic`, `bootstrap_servers` |
| `doris` | Apache Doris Stream Load | `host`, `database`, `table` |

多个 sink 可同时使用：

```python
sinks = [
    {"type": "csv", "path": "./data.csv"},
    {"type": "kafka", "topic": "products", "bootstrap_servers": "kafka:9092"},
]
```

## 编码处理

老旧站点自动检测编码，也可手动指定：

```python
class OldSiteSpider(BaseSpider):
    name = "old_site"
    start_urls = ["http://old-site.com"]
    # encoding = "gbk"  # 手动指定编码（一般不需要，自动检测）
```

自动检测优先级：HTTP Content-Type charset → HTML meta charset → charset-normalizer 推断 → UTF-8

## 表单提交

```python
async def run(self):
    page = await self.get("http://site.com/login")
    # 自动提取隐藏字段（ViewState、CSRF token 等）
    form_data = self.auto_fill_form(page, "form#login", {
        "username": "admin",
        "password": "123456",
    })
    result = await self.post("http://site.com/login", data=form_data)
```

## 响应元数据

```python
page = await self.get(url)
page.status           # HTTP 状态码
page.headers          # 响应头
page.cookies          # 响应 Cookie
page.url              # 最终 URL（重定向后）
page.body             # 原始响应体 bytes
page.encoding         # 响应编码
page.captured_xhr     # 捕获的 XHR 响应列表
```

## 多 Session 路由

同一爬虫内混合使用 HTTP 和浏览器：

```python
class MixedSpider(BaseSpider):
    name = "mixed"
    use_stealth = False  # 默认 HTTP

    async def run(self):
        # HTTP 请求（快，轻量）
        list_page = await self.get("https://site.com/list")

        # 需要浏览器时，用 stealth session
        detail = await self.get("https://site.com/detail", stealth=True)
        yield {"content": detail.css(".content").get("")}
```

## 开发调试模式

```python
class DebugSpider(BaseSpider):
    name = "debug"
    development_mode = True  # 缓存响应到磁盘，开发调试免重请求
```

## 全部配置属性

```python
class MySpider(BaseSpider):
    # === 基本信息 ===
    name = "my_spider"               # 唯一标识（必填）
    description = "爬虫描述"          # 描述信息
    start_urls = ["https://..."]      # 起始 URL 列表
    schedule = "0 */6 * * *"         # cron 表达式（可选，None=手动触发）

    # === 请求控制 ===
    max_retries = 3                   # 失败重试次数
    retry_delay = 60                  # 重试间隔（秒）
    concurrent_requests = 4           # 并发请求数
    download_delay = 0.5              # 请求间隔（秒）
    timeout = 30                      # 请求超时（秒）
    ssl_verify = True                 # SSL 证书验证
    follow_redirects = True           # 跟随重定向
    allow_internal_redirects = False  # 允许重定向到内网 IP（Scrapling 默认阻止 SSRF）

    # === 请求头/Cookie ===
    default_headers = {}              # 自定义请求头
    cookies = {}                      # 预设 Cookie

    # === 反爬与指纹 ===
    impersonate = "chrome"            # TLS 指纹（chrome/firefox/safari/edge）
    http3 = False                     # HTTP/3
    stealthy_headers = True           # 真实浏览器请求头
    block_ads = False                 # 屏蔽广告域名
    blocked_domains = set()           # 自定义屏蔽域名
    dns_over_https = False            # DNS over HTTPS
    locale = None                     # 浏览器语言（如 "zh-CN"）
    timezone_id = None                # 浏览器时区（如 "Asia/Shanghai"）
    proxies = []                      # 代理列表（多个自动轮换）

    # === 浏览器模式（use_stealth=True 时生效） ===
    use_stealth = False               # 启用隐身浏览器
    solve_cloudflare = False          # 自动破解 Cloudflare
    block_webrtc = False              # 阻断 WebRTC
    hide_canvas = False               # Canvas 噪声
    allow_webgl = True                # 允许 WebGL
    real_chrome = False               # 使用真实 Chrome
    cdp_url = None                    # CDP 远程浏览器地址
    user_data_dir = None              # 浏览器数据目录（持久化 Cookie）
    init_script = None                # 页面创建前注入 JS
    max_pages = 1                     # 标签页池大小
    disable_resources = True          # 屏蔽图片/字体/媒体
    network_idle = False              # 等待网络空闲
    load_dom = True                   # 等待 DOM 加载
    wait_selector = None              # 等待指定元素出现
    wait_selector_state = "attached"  # 等待状态
    wait = 0                          # 额外等待毫秒
    page_action = None                # 页面加载后执行（Playwright 操作）
    page_setup = None                 # 页面导航前执行
    capture_xhr = None                # XHR 拦截 URL 正则

    # === 自适应 ===
    adaptive = False                  # 自适应选择器
    adaptive_storage = None           # 自适应数据库路径

    # === 数据 ===
    crawl_mode = "incremental"        # incremental | full（全量清空表）
    fields = []                       # 字段定义（自动建表）
    dedup_key = None                  # 去重键
    sinks = []                        # 数据管道（不配置则默认写数据库）
    schema = {}                       # 数据 schema
    primary_key = []                  # 主键

    # === 开发 ===
    development_mode = False          # 缓存响应到磁盘
```

## 注意事项

- `run()` 是异步生成器，用 `yield` 返回数据项
- 循环中检查 `self.should_stop` 以支持优雅停止
- `self.get()`/`self.post()` 必须在 `run()` 内调用（session 由 Runner 注入）
- 文件保存到 `spiders/` 目录后自动注册
- 爬虫名 `name` 必须唯一
- 不配置 `sinks` 且定义了 `fields` → 自动写入数据库
- 配置了 `sinks` → 只写 sinks，不写数据库
- `use_stealth=True` 时 `get()`/`post()` 自动使用浏览器
- 失败自动重试（`max_retries` 次，指数退避）
- 暂停后可恢复（利用 Scrapling crawldir 断点机制）

---

# OpenSpider API 参考

所有需要认证的接口在 Header 中携带：`Authorization: Bearer <access_token>`

## 认证

### 登录

```
POST /auth/login/json
Content-Type: application/json

{"username": "admin", "password": "123456"}
```

响应：
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 刷新 Token

```
POST /auth/refresh
Content-Type: application/json

{"refresh_token": "<refresh_token>"}
```

### 注册

```
POST /auth/register
Content-Type: application/json

{"username": "user1", "email": "u@example.com", "password": "123456", "display_name": "用户1"}
```

### 获取当前用户

```
GET /auth/me
```

### 修改密码

```
PUT /auth/me/password
Content-Type: application/json

{"old_password": "123456", "new_password": "654321"}
```

## 爬虫管理

### 列出爬虫

```
GET /spiders
```

响应：
```json
{
  "spiders": [
    {
      "id": 1,
      "name": "my_spider",
      "description": "抓取示例网站",
      "schedule": "0 */6 * * *",
      "is_running": false,
      "is_public": false,
      "items_scraped": 100,
      "requests_made": 50,
      "errors_count": 0
    }
  ],
  "total": 1
}
```

### 获取爬虫详情

```
GET /spiders/{name}
```

### 通过代码字符串创建爬虫

```
POST /spiders/create
Content-Type: application/json

{
  "filename": "my_spider.py",
  "code": "from openspider.spiders.base import BaseSpider\n\nclass MySpider(BaseSpider):\n    name = 'my_spider'\n    start_urls = ['https://example.com']\n\n    async def run(self):\n        page = await self.get(self.start_urls[0])\n        for item in page.css('.article'):\n            yield {'title': item.css('h2::text').get('')}\n"
}
```

响应：
```json
{
  "success": true,
  "message": "创建成功，注册了 1 个爬虫",
  "registered_spiders": ["my_spider"]
}
```

### 通过文件上传创建爬虫

```
POST /spiders/upload
Content-Type: multipart/form-data

file=@my_spider.py
```

### 获取爬虫源代码

```
GET /spiders/{spider_id}/code
```

### 启动爬虫

```
POST /spiders/{spider_id}/start
Content-Type: application/json

{"params": {"keyword": "python"}}
```

响应：
```json
{
  "success": true,
  "message": "爬虫 my_spider 已启动",
  "task_id": 42
}
```

### 停止爬虫

```
POST /spiders/{spider_id}/stop
```

### 暂停爬虫（断点保留）

```
POST /spiders/{spider_id}/pause
```

### 恢复爬虫（从断点继续）

```
POST /spiders/{spider_id}/resume
```

### 删除爬虫

```
DELETE /spiders/{spider_id}
```

### 设置爬虫公开/私有

```
PUT /spiders/{spider_id}/visibility
Content-Type: application/json

{"is_public": true}
```

## 任务查询

### 任务列表

```
GET /tasks?spider=my_spider&status=running&limit=50&offset=0
```

响应：
```json
{
  "tasks": [
    {
      "id": 42,
      "spider_name": "my_spider",
      "status": "completed",
      "created_at": "2024-01-01T00:00:00",
      "started_at": "2024-01-01T00:00:01",
      "finished_at": "2024-01-01T00:05:00",
      "items_scraped": 100,
      "requests_made": 50,
      "errors_count": 0,
      "params": {}
    }
  ],
  "total": 1
}
```

### 任务详情

```
GET /tasks/{task_id}
```

### 任务日志

```
GET /tasks/{task_id}/logs?limit=100
```

## 数据查询

### 查询爬虫数据

```
GET /spiders/{spider_id}/data?page=1&page_size=50
```

响应：
```json
{
  "items": [{"title": "示例标题", "url": "https://..."}],
  "total": 100,
  "page": 1,
  "page_size": 50,
  "columns": ["title", "url"]
}
```

### 导出爬虫数据

```
GET /spiders/{spider_id}/export?format=json&limit=10000
```

支持格式：`json`（默认）、`jsonl`、`csv`

### 获取爬虫字段定义

```
GET /spiders/{spider_id}/fields
```

## 调度管理

### 列出调度

```
GET /schedules
```

### 创建调度

```
POST /schedules
Content-Type: application/json

{
  "spider_name": "my_spider",
  "cron": "0 */6 * * *",
  "params": {"keyword": "python"}
}
```

### 更新调度

```
PUT /schedules/{schedule_id}
Content-Type: application/json

{"cron": "0 */12 * * *", "params": {"keyword": "java"}}
```

### 删除调度

```
DELETE /schedules/{schedule_id}
```

### 启用调度

```
POST /schedules/{schedule_id}/enable
```

### 禁用调度

```
POST /schedules/{schedule_id}/disable
```

### 调度执行记录

```
GET /schedules/{schedule_id}/runs?limit=10
```

## 系统

### 健康检查（无需认证）

```
GET /health
```

### 平台能力描述（无需认证）

```
GET /capabilities
```

返回平台支持的爬虫接口、配置属性、API 列表等，供 AI 调用时参考。
