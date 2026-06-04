---
name: openspider
description: |
  通过 OpenSpider 平台管理爬虫。当用户想要创建、运行、停止、监控爬虫或导出爬取数据时使用此 Skill。当用户提到爬取网站、抓取数据、编写爬虫、自动化数据采集、管理多个爬虫任务时，都应使用此 Skill。即使用户只是说"我需要从这个网站获取数据"或"帮我抓取 X"，也应该使用此 Skill。平台基于 Scrapling 构建，支持反爬绕过、Cloudflare 破解、浏览器指纹伪装、并发爬取、暂停恢复等能力。
---

# OpenSpider 爬虫管理平台

基于 Scrapling 构建的爬虫管理平台。管理多个爬虫的完整生命周期——注册、启停、暂停恢复、失败重试、定时调度、数据导出，通过标准 HTTP API 暴露所有能力。

底层使用 Scrapling 的 Spider 框架执行爬取，复用其并发调度、请求去重、代理轮换、暂停恢复（crawldir）等能力，不在上层造轮子。

## 快速参考

**API 地址**：`http://localhost:8088`
**API 文档**：`http://localhost:8088/docs`

## 核心流程

1. **分析目标** — 抓取页面，检查结构，确定选择器和反爬等级
2. **编写爬虫** — 继承 `BaseSpider`，实现 `run()` 或 `parse()`
3. **上传** — `POST /spiders/upload`
4. **启动** — `POST /spiders/{name}/start`
5. **监控** — 轮询 `GET /tasks?spider={name}`
6. **获取数据** — `GET /items?spider={name}`

## 编写爬虫代码

所有爬虫继承 `BaseSpider`。底层自动创建 Scrapling Spider 子类执行，复用其并发/去重/代理/暂停恢复。

### 简单模式 — run()

```python
from openspider.spiders.base import BaseSpider

class MySpider(BaseSpider):
    name = "my_spider"
    start_urls = ["https://example.com"]

    async def run(self):
        page = await self.get(self.start_urls[0])
        for item in page.css(".article"):
            if self.should_stop:
                break
            yield {"title": item.css("h2::text").get("")}
```

### 高级模式 — parse(response) 回调

适合多级页面跟进、列表→详情、自动翻页。yield Request 自动加入 Scrapling 的请求队列，享受并发、去重、代理轮换：

```python
class BlogSpider(BaseSpider):
    name = "blog"
    start_urls = ["https://example.com/posts"]

    async def parse(self, response):
        for link in response.css("a.post-link::attr(href)").getall():
            yield self.follow(link, callback=self.parse_post)
        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            yield self.follow(next_page, callback=self.parse)

    async def parse_post(self, response):
        yield {"title": response.css("h1::text").get(""), "url": response.url}
```

自动识别：实现 `parse()` 走回调模式，否则走 `run()` 模式。两种模式都通过 Scrapling Spider 执行。

### 可用方法

| 方法 | 说明 |
|------|------|
| `await self.get(url, **kwargs)` | HTTP GET，返回 Scrapling Response |
| `await self.post(url, **kwargs)` | HTTP POST，返回 Scrapling Response |
| `self.follow(url, callback=)` | 创建跟进请求，自动解析相对 URL + Referer（委托 Scrapling response.follow） |
| `self.request(url, callback=)` | 创建 Scrapling Request 对象 |
| `self.should_stop` | 检查停止信号 |
| `self.session` | Scrapling session 实例 |
| `self.env(key, default=None)` | 读取环境变量（敏感参数） |
| `self.params` | 运行时参数字典（API/CLI 传入） |

### 三层参数体系

**静态配置** — 类属性：
```python
class MySpider(BaseSpider):
    name = "my_spider"
    concurrent_requests = 4  # Scrapling 并发数
    use_stealth = True       # Scrapling 隐身模式
```

**运行时参数** — API/CLI 传入：
```python
async def run(self):
    keyword = self.params.get("keyword", "default")
```
`POST /spiders/search/start` Body: `{"params": {"keyword": "Python"}}`

**敏感参数** — 环境变量：
```python
async def run(self):
    api_key = self.env("API_KEY")
```

### 生命周期钩子

| 钩子 | 触发时机 |
|------|----------|
| `on_start(resuming=False)` | 启动前 |
| `on_error(error)` | 异常时 |
| `on_complete()` | 完成后 |
| `on_item_scraped(item)` | 每条数据后处理，返回 None 丢弃 |

### 配置属性

**基本：**

| 属性 | 默认值 | 说明 |
|------|--------|------|
| `name` | 必填 | 唯一标识 |
| `start_urls` | `[]` | 入口 URL（Scrapling Spider 自动遍历） |
| `concurrent_requests` | `4` | Scrapling 并发请求数 |
| `download_delay` | `0.5` | Scrapling 请求间隔秒数 |
| `robots_txt_obey` | `False` | Scrapling 遵守 robots.txt |
| `proxies` | `[]` | 代理列表（多个时自动使用 Scrapling ProxyRotator 轮换） |
| `schedule` | `None` | cron 表达式 |
| `max_retries` | `3` | 平台级重试次数 |
| `development_mode` | `False` | Scrapling 响应缓存（开发调试用） |

**反爬与浏览器（Scrapling StealthyFetcher）：**

| 属性 | 默认值 | 说明 |
|------|--------|------|
| `use_stealth` | `False` | Scrapling 隐身浏览器模式 |
| `impersonate` | `"chrome"` | Scrapling TLS 指纹伪装 |
| `solve_cloudflare` | `False` | Scrapling 自动破解 Cloudflare |
| `block_webrtc` | `False` | Scrapling 阻断 WebRTC |
| `hide_canvas` | `False` | Scrapling Canvas 噪声 |
| `real_chrome` | `False` | Scrapling 使用真实 Chrome |
| `block_ads` | `False` | Scrapling 屏蔽 3500+ 广告域名 |
| `capture_xhr` | `None` | Scrapling XHR 拦截 URL 正则 |
| `max_pages` | `1` | Scrapling 浏览器标签页池 |

**站点兼容（Scrapling FetcherSession）：**

| 属性 | 默认值 | 说明 |
|------|--------|------|
| `ssl_verify` | `True` | SSL 证书验证 |
| `timeout` | `30` | 超时秒数 |
| `default_headers` | `{}` | 默认请求头 |
| `cookies` | `{}` | 预设 Cookie |
| `network_idle` | `False` | 等待网络空闲 |
| `wait_selector` | `None` | 等待选择器出现 |

## 模式选择

- **静态 HTML** → 默认模式
- **JS 动态加载** → `network_idle=True` 或 `wait_selector=".content"`
- **反爬保护** → `use_stealth=True`，`solve_cloudflare=True`
- **SPA API 数据** → `capture_xhr=r"https://api\.example\.com/.*"`
- **SSL 证书问题** → `ssl_verify=False`
- **真实浏览器** → `use_stealth=True`，`real_chrome=True`，`block_webrtc=True`

## 模板爬虫

### RuleSpider（Scrapling CrawlSpider 包装）

```python
from openspider.spiders.templates import RuleSpider
from scrapling.spiders import CrawlRule, LinkExtractor

class BlogCrawler(RuleSpider):
    name = "blog"
    start_urls = ["https://example.com"]
    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
            CrawlRule(LinkExtractor(allow=r"/page/\d+/")),
        ]
    async def parse_post(self, response):
        yield {"title": response.css("h1::text").get("")}
```

### SitemapRuleSpider（Scrapling SitemapSpider 包装）

```python
from openspider.spiders.templates import SitemapRuleSpider
from scrapling.spiders import CrawlRule, LinkExtractor

class ProductSitemap(SitemapRuleSpider):
    name = "products"
    sitemap_urls = ["https://shop.example.com/sitemap.xml"]
    def rules(self):
        return [CrawlRule(LinkExtractor(allow=r"/products/"), callback=self.parse_product)]
    async def parse_product(self, response):
        yield {"name": response.css("h1::text").get("")}
```

模板爬虫通过 `configure_sessions()` 转发所有配置（代理、隐身、超时等）给 Scrapling。

## API 接口

```
GET    /spiders                  # 列出所有爬虫
POST   /spiders/{name}/start     # 启动（Body: {"params": {...}}）
POST   /spiders/{name}/stop      # 停止
POST   /spiders/{name}/pause     # 暂停（crawldir 保留断点）
DELETE /spiders/{name}           # 删除
POST   /spiders/upload           # 上传 .py 文件
GET    /tasks?spider=&status=    # 任务列表
GET    /tasks/{id}/logs          # 任务日志
GET    /items?spider=            # 数据查询
GET    /export/{name}?format=    # 导出（json/jsonl/csv）
GET    /health                   # 健康检查
GET    /capabilities             # 能力描述（给 AI）
```

## CLI

```bash
openspider serve                      # 启动平台
openspider list                       # 列出爬虫
openspider start <name> [-p k=v]     # 启动（可传参数）
openspider stop <name>               # 停止
openspider info <name>               # 详情
openspider tasks [--spider=]         # 任务列表
openspider logs <task_id>            # 任务日志
openspider export <name> --format=   # 导出数据
openspider add <file.py>             # 注册爬虫
openspider validate <file.py>        # 校验文件
```

## 辅助工具

- **`openspider.utils.form`** — 表单字段提取、隐藏字段收集、ASP.NET ViewState 提取
- **`openspider.utils.url`** — jsessionid 剥离、URL 拼接和规范化
- **`openspider.utils.selector`** — `find_by_text`、`find_by_regex`、`find_similar` 增强查找

## 数据管道（Sinks）

爬取数据可同时写入多个目标。在爬虫上声明 `sinks` 和 `schema`：

```python
class NewsSpider(BaseSpider):
    name = "news"
    schema = {"url": "string", "title": "string", "content": "text"}
    primary_key = ["url"]  # 有主键则 upsert，无则追加
    sinks = [
        {"type": "csv", "path": "./data/news.csv"},
        {"type": "excel", "path": "./data/news.xlsx"},
        {"type": "kafka", "topic": "news_data", "bootstrap_servers": "localhost:9092"},
        {"type": "doris", "host": "localhost", "database": "crawl", "table": "news"},
        {"type": "json", "path": "./data/news.jsonl"},
    ]
```

| Sink | 说明 | 自动创建 |
|------|------|----------|
| `csv` | CSV 文件追加写入 | 自动创建目录 |
| `excel` | Excel 文件（需 openpyxl） | 自动创建 |
| `json` | JSON/JSONL 文件 | 自动创建 |
| `kafka` | Kafka topic（需 aiokafka） | `auto_create=True` 自动建 topic |
| `doris` | Doris HTTP Stream Load | `auto_create=True` 自动建表 |

不配置 sinks 则只写默认 MySQL items 表。主键类型映射：`string→VARCHAR(500)`、`text→TEXT`、`int→BIGINT`、`float→DOUBLE`、`datetime→DATETIME`。

## 定时任务（Schedules）

```
GET    /schedules                 # 列出调度
POST   /schedules                 # 创建（Body: {"spider_name":"x","cron":"0 */6 * * *","params":{}}）
PUT    /schedules/{id}            # 修改
DELETE /schedules/{id}            # 删除
POST   /schedules/{id}/enable     # 启用
POST   /schedules/{id}/disable    # 禁用
GET    /schedules/{id}/runs       # 执行历史
```

也可在爬虫类上静态声明：`schedule = "0 */6 * * *"`。动态调度优先级高于静态。

## 用户隔离

平台通过 `X-User-Id` 请求头传递用户标识，OpenSpider 按用户隔离数据：

- `GET /spiders` 只返回自己的爬虫
- `POST /spiders/upload` 自动设置 owner
- `GET /items` 只返回自己的数据
- 管理员用 `X-Api-Key`（admin_api_key）可看所有
