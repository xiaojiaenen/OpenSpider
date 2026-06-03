---
name: openspider
description: |
  通过 OpenSpider 平台管理爬虫。当用户想要创建、运行、停止、监控爬虫或导出爬取数据时使用此 Skill。当用户提到爬取网站、抓取数据、编写爬虫、自动化数据采集、管理多个爬虫任务时，都应使用此 Skill。即使用户只是说"我需要从这个网站获取数据"或"帮我抓取 X"，也应该使用此 Skill。
---

# OpenSpider 爬虫管理平台

OpenSpider 是一个爬虫管理平台，管理多个爬虫的完整生命周期——注册、启停、暂停恢复、失败重试、定时调度、数据导出，通过标准 HTTP API 暴露所有能力。

你的职责是帮助用户编写爬虫代码、上传到平台、管理运行中的爬虫、获取爬取数据。

## 快速参考

**API 地址**：`http://localhost:8088`
**API 文档**：`http://localhost:8088/docs`

## 核心流程

当用户要求爬取某个网站时，按以下步骤执行：

1. **分析目标** — 抓取页面，检查结构，确定要提取的数据和选择器。判断网站是否使用 JS 渲染、是否有反爬机制、是否使用非 UTF-8 编码。
2. **编写爬虫** — 创建 `.py` 文件，继承 `BaseSpider`，实现 `run()` 方法。根据网站特性配置：反爬站设 `use_stealth=True`，老站点设 `encoding`，SPA 站点用 `capture_xhr` 等。
3. **上传** — `POST /spiders/upload` 上传 `.py` 文件。
4. **启动** — `POST /spiders/{name}/start`。
5. **监控** — 轮询 `GET /tasks?spider={name}` 直到状态为 `completed` 或 `failed`。
6. **获取数据** — `GET /items?spider={name}` 获取数据，`GET /tasks/{id}/logs` 查看错误日志。

## 编写爬虫代码

所有爬虫继承 `BaseSpider`，支持两种编写模式：

### 简单模式 — run() 异步生成器

适合简单场景，直接请求 + yield 数据项：

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

### 高级模式 — parse(response) 回调模式

适合复杂场景：多级页面跟进、列表→详情、自动翻页：

```python
class BlogSpider(BaseSpider):
    name = "blog"
    start_urls = ["https://example.com/posts"]

    async def parse(self, response):
        """列表页：提取链接 + 跟进分页"""
        for link in response.css("a.post-link::attr(href)").getall():
            yield self.follow(link, callback=self.parse_post)  # 跟进到详情页

        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            yield self.follow(next_page, callback=self.parse)  # 翻页

    async def parse_post(self, response):
        """详情页：提取数据"""
        yield {
            "title": response.css("h1::text").get(""),
            "content": response.css("article").get(""),
            "url": response.url,
        }
```

两种模式自动识别：实现 `parse()` 走回调模式，否则走 `run()` 模式。

### 可用方法

| 方法 | 说明 |
|------|------|
| `await self.get(url, **kwargs)` | HTTP GET 请求，返回 Scrapling Response 对象 |
| `await self.post(url, **kwargs)` | HTTP POST 请求，返回 Scrapling Response 对象 |
| `self.follow(url, callback=)` | 创建跟进请求（高级模式用），自动处理相对 URL 和 Referer |
| `self.request(url, callback=)` | 创建 Request 对象（高级模式用） |
| `await self.concurrent_fetch(urls, max_concurrent=10)` | 并发抓取多个 URL |
| `self.should_stop` | 返回 `True` 表示收到停止信号 |
| `self.session` | 底层 Scrapling session，用于高级操作 |
| `self.env(key, default=None)` | 读取环境变量（用于 API Key、密码等敏感参数） |
| `self.params` | 运行时参数字典（通过 API/CLI 传入） |

### 三层参数体系

爬虫参数分三层，各有适用场景：

**第一层：静态配置** — 写在类属性上，不常变：
```python
class MySpider(BaseSpider):
    name = "my_spider"
    concurrent_requests = 4
    use_stealth = True
    encoding = "gbk"
```

**第二层：运行时参数** — 每次启动可不同，通过 API 或 CLI 传入：
```python
class SearchSpider(BaseSpider):
    name = "search"
    async def run(self):
        keyword = self.params.get("keyword", "default")
        max_pages = int(self.params.get("max_pages", "10"))
```
API 调用：`POST /spiders/search/start` Body: `{"params": {"keyword": "Python", "max_pages": "5"}}`
CLI 调用：`openspider start search -p keyword=Python -p max_pages=5`

**第三层：敏感参数** — 通过环境变量传入，不走 API，不入库：
```python
class ApiSpider(BaseSpider):
    name = "api_spider"
    async def run(self):
        api_key = self.env("API_KEY")
        secret = self.env("SECRET", "default_value")
```
启动时设置：`API_KEY=xxx openspider start api_spider`

### 生命周期钩子

| 钩子 | 触发时机 |
|------|----------|
| `on_start(resuming=False)` | 爬虫启动前。`resuming=True` 表示从断点恢复。 |
| `on_error(error)` | 爬取过程中发生异常时。 |
| `on_complete()` | 爬取完成后（无论成功或失败）。 |
| `on_item_scraped(item) -> dict\|None` | 每条数据后处理。返回 `None` 丢弃该条。 |

### 关键配置属性

这些是设置在爬虫类上的类属性。

**基本配置：**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 爬虫唯一标识 |
| `description` | str | `""` | 爬虫描述 |
| `start_urls` | list[str] | `[]` | 入口 URL 列表 |
| `schedule` | str | `None` | cron 表达式，如 `"0 */6 * * *"`（每6小时） |
| `max_retries` | int | `3` | 失败重试次数 |
| `retry_delay` | int | `60` | 重试间隔秒数（自动指数退避） |
| `concurrent_requests` | int | `4` | 最大并发请求数 |
| `download_delay` | float | `0.5` | 请求间隔秒数 |
| `proxies` | list[str] | `[]` | 代理列表 |

**反爬与浏览器：**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `use_stealth` | bool | `False` | 使用隐身浏览器模式（可绕过 Cloudflare 等） |
| `impersonate` | str | `"chrome"` | TLS 指纹伪装（`chrome`/`firefox`/`safari`/`edge`） |
| `solve_cloudflare` | bool | `False` | 自动破解 Cloudflare 挑战（需配合 `use_stealth=True`） |
| `block_webrtc` | bool | `False` | 阻断 WebRTC 防止真实 IP 泄露 |
| `hide_canvas` | bool | `False` | Canvas 噪声防止指纹追踪 |
| `real_chrome` | bool | `False` | 使用设备上真实 Chrome 而非内置 Chromium |
| `block_ads` | bool | `False` | 屏蔽约 3500 个广告/追踪域名 |
| `capture_xhr` | str | `None` | XHR/Fetch 拦截的 URL 正则（用于 SPA 站点） |
| `max_pages` | int | `1` | 浏览器标签页池大小 |

**网站兼容（老旧/问题站点）：**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `encoding` | str | `None` | 强制编码（如 `"gbk"`、`"big5"`、`"shift_jis"`） |
| `ssl_verify` | bool | `True` | 跳过 SSL 证书验证 |
| `timeout` | int | `30` | 请求超时秒数 |
| `default_headers` | dict | `{}` | 自定义默认请求头 |
| `cookies` | dict | `{}` | 预设 Cookie |
| `network_idle` | bool | `False` | 等待网络空闲再返回（JS 重度站点） |
| `wait_selector` | str | `None` | 等待指定 CSS 选择器出现再返回 |
| `wait` | int | `0` | 页面加载后额外等待毫秒数 |

**自适应爬取：**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `adaptive` | bool | `False` | 启用自适应选择器——网站改版后自动定位元素 |

## 模式选择

编写爬虫时，根据网站特性选择合适的模式：

- **静态 HTML，不需要 JS** → 默认模式（不设特殊标志）
- **内容由 JS 动态加载** → `network_idle=True` 或 `wait_selector=".content"`
- **有反爬保护（Cloudflare 等）** → `use_stealth=True`，`solve_cloudflare=True`
- **SPA 通过 API 加载数据** → `capture_xhr=r"https://api\.example\.com/.*"` 拦截 XHR
- **老旧站点使用 GBK/Big5 编码** → `encoding="gbk"`
- **SSL 证书过期的站点** → `ssl_verify=False`
- **需要模拟真实浏览器** → `use_stealth=True`，`real_chrome=True`，`block_webrtc=True`

## 模板爬虫

对于常见的爬取模式，使用模板爬虫避免重复代码：

### RuleSpider（按规则跟进链接）

```python
from openspider.spiders.templates import RuleSpider
from scrapling.spiders import CrawlRule, LinkExtractor

class BlogCrawler(RuleSpider):
    name = "blog"
    start_urls = ["https://example.com"]

    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
            CrawlRule(LinkExtractor(allow=r"/page/\d+/")),  # 只跟进，不解析
        ]

    async def parse_post(self, response):
        yield {"title": response.css("h1::text").get("")}
```

### SitemapRuleSpider（从 sitemap.xml 驱动爬取）

```python
from openspider.spiders.templates import SitemapRuleSpider
from scrapling.spiders import CrawlRule, LinkExtractor

class ProductSitemap(SitemapRuleSpider):
    name = "products"
    sitemap_urls = ["https://shop.example.com/sitemap.xml"]

    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/products/"), callback=self.parse_product),
        ]

    async def parse_product(self, response):
        yield {"name": response.css("h1::text").get(""), "price": response.css(".price::text").get("")}
```

## API 接口

### 爬虫管理

```
GET    /spiders                  # 列出所有爬虫
GET    /spiders/{name}           # 爬虫详情
POST   /spiders/{name}/start     # 启动爬虫（Body: {"params": {"key": "value"}}）
POST   /spiders/{name}/stop      # 停止爬虫
POST   /spiders/{name}/pause     # 暂停爬虫（可恢复）
DELETE /spiders/{name}           # 删除爬虫（运行中会先停止）
POST   /spiders/upload           # 上传 .py 爬虫文件
```

### 任务查询

```
GET    /tasks                    # 任务列表（?spider=&status=）
GET    /tasks/{id}               # 任务详情
GET    /tasks/{id}/logs          # 任务日志
```

### 数据

```
GET    /items                    # 查询爬取数据（?spider=&task_id=&page=&page_size=）
GET    /export/{name}            # 导出数据（?format=json|jsonl|csv）
```

### 系统

```
GET    /health                   # 健康检查（MySQL 状态、活跃爬虫数）
GET    /capabilities             # 平台能力描述（供 AI 集成使用）
```

## CLI 命令

```bash
openspider serve                  # 启动平台（API + 调度器 + 文件监控）
openspider list                   # 列出所有爬虫
openspider start <name>           # 启动爬虫
openspider stop <name>            # 停止爬虫
openspider info <name>            # 查看爬虫详情
openspider add <file.py>          # 注册新爬虫文件
openspider validate <file.py>     # 校验爬虫文件（不注册）
```

## 辅助工具

以下工具模块位于 `openspider/utils/`，可在爬虫代码中使用：

- **`openspider.utils.form`** — `extract_form_fields(response)` 提取表单字段、`extract_hidden_fields(response)` 提取隐藏字段、`extract_asp_viewstate(response)` 提取 ASP.NET ViewState、`merge_form_data(hidden, user_data)` 合并表单数据 — 用于 ASP.NET/JSP/PHP 表单提交
- **`openspider.utils.url`** — `strip_jsessionid(url)` 剥离 jsessionid、`resolve_url(base, relative)` 相对 URL 拼接、`normalize_url(url)` URL 规范化
- **`openspider.utils.selector`** — `find_by_text(response, text)` 按文本查找、`find_by_regex(response, pattern)` 按正则查找、`find_similar(response, element)` 查找相似元素 — CSS/XPath 之外的增强查找方式
