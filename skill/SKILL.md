# OpenSpider — AI 集成 Skill 描述

## 平台简介

OpenSpider 是一个爬虫管理平台，管理多个爬虫的生命周期（注册、启停、暂停恢复、失败重试、数据导出），并通过标准化 API 暴露能力给外部 AI 集成。

## API 基础地址

默认 `http://localhost:8000`，API 文档 `http://localhost:8000/docs`

## 集成流程

1. **GET /capabilities** — 获取平台能力描述和爬虫接口规范
2. **分析目标网站** — AI 自行完成（fetch + 分析 HTML 结构）
3. **生成爬虫代码** — 按下方接口规范生成 `.py` 文件
4. **POST /spiders/upload** — 上传爬虫文件到平台
5. **POST /spiders/{name}/start** — 启动爬虫
6. **GET /items?spider={name}** — 获取爬取结果
7. **GET /tasks/{id}** — 查看运行状态和错误

## 爬虫接口规范

所有爬虫必须继承 `BaseSpider` 并实现 `run()` 方法。

### 必填属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | str | 唯一标识，如 `"news_spider"` |

### 可选属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | str | `""` | 爬虫描述 |
| `start_urls` | list[str] | `[]` | 入口 URL 列表 |
| `schedule` | str | `None` | cron 表达式，如 `"0 */6 * * *"` |
| `max_retries` | int | `3` | 失败重试次数 |
| `retry_delay` | int | `60` | 重试间隔（秒） |
| `concurrent_requests` | int | `4` | 并发请求数 |
| `download_delay` | float | `0.5` | 请求间隔（秒） |
| `use_stealth` | bool | `False` | 使用隐身浏览器模式 |
| `proxies` | list[str] | `[]` | 代理列表 |
| `encoding` | str | `None` | 强制编码（如 `gbk`） |
| `ssl_verify` | bool | `True` | 验证 SSL 证书 |
| `timeout` | int | `30` | 请求超时秒数 |
| `impersonate` | str | `"chrome"` | TLS 指纹伪装 |
| `solve_cloudflare` | bool | `False` | 自动破解 Cloudflare |
| `block_ads` | bool | `False` | 屏蔽广告域名 |
| `capture_xhr` | str | `None` | XHR 拦截 URL 正则 |
| `adaptive` | bool | `False` | 自适应选择器 |

### run() 方法

```python
async def run(self) -> AsyncGenerator[dict, None]:
    """核心爬取逻辑，yield 数据项"""
    page = await self.get("https://example.com")
    for item in page.css(".article"):
        yield {"title": item.css("h2::text").get("")}
```

### 可用方法

| 方法 | 说明 |
|------|------|
| `await self.get(url, **kwargs)` | HTTP GET 请求 |
| `await self.post(url, **kwargs)` | HTTP POST 请求 |
| `self.should_stop` | 检查是否收到停止信号 |
| `self.session` | Scrapling session 实例 |

### 钩子方法

| 方法 | 说明 |
|------|------|
| `on_start(resuming=False)` | 启动前 |
| `on_error(error)` | 出错时 |
| `on_complete()` | 完成时 |
| `on_item_scraped(item)` | 每条数据后处理，返回 None 丢弃 |

## API 接口

### 爬虫管理

```
GET    /spiders              # 列出所有爬虫
GET    /spiders/{name}       # 爬虫详情
POST   /spiders/{name}/start # 启动
POST   /spiders/{name}/stop  # 停止
POST   /spiders/{name}/pause # 暂停
DELETE /spiders/{name}       # 删除
POST   /spiders/upload       # 上传 .py 文件
```

### 任务查询

```
GET    /tasks                # 任务列表（?spider=&status=）
GET    /tasks/{id}           # 任务详情
GET    /tasks/{id}/logs      # 任务日志
```

### 数据

```
GET    /items                # 数据查询（?spider=&task_id=&page=&page_size=）
GET    /export/{name}        # 导出（?format=json|jsonl|csv）
```

### 系统

```
GET    /health               # 健康检查
GET    /capabilities         # 能力描述
```

## 完整爬虫示例

```python
from openspider.spiders.base import BaseSpider

class NewsSpider(BaseSpider):
    name = "news"
    description = "新闻爬虫"
    start_urls = ["https://news.example.com"]
    concurrent_requests = 4
    download_delay = 1.0
    use_stealth = True
    solve_cloudflare = True
    block_ads = True

    async def run(self):
        for url in self.start_urls:
            if self.should_stop:
                break
            page = await self.get(url)
            for article in page.css("article"):
                link = article.css("a::attr(href)").get()
                if link:
                    detail = await self.get(link)
                    yield {
                        "title": detail.css("h1::text").get(""),
                        "content": detail.css(".content").get(""),
                        "url": link,
                    }
```
