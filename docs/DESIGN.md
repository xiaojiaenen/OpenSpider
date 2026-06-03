# OpenSpider 设计方案

## 项目定位

OpenSpider 是一个**爬虫管理平台**，核心职责是：管理多个爬虫的生命周期（注册、启停、暂停恢复、失败重试、数据导出），并通过标准化 API 暴露能力给外部 AI 或其他系统集成。

平台本身不包含 AI 逻辑。AI 通过 API/CLI 调用平台能力来完成网站分析、爬虫生成、运行管理等工作。

---

## 架构总览

```
外部 AI / 调度系统 / 人工操作
        │
        │  HTTP API / CLI / MCP Server
        ▼
┌──────────────────────────────────────────────┐
│                OpenSpider Platform            │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ API 层   │  │ CLI 层   │  │ MCP Server│  │
│  │ (FastAPI)│  │ (Click)  │  │ (可选)    │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       │              │              │         │
│       └──────────────┼──────────────┘         │
│                      ▼                        │
│  ┌─────────────────────────────────────────┐  │
│  │            Core Engine                  │  │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────┐ │  │
│  │  │ Registry │ │Scheduler │ │Recovery │ │  │
│  │  │ 爬虫注册 │ │ 任务调度 │ │ 失败恢复│ │  │
│  │  └──────────┘ └──────────┘ └─────────┘ │  │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────┐ │  │
│  │  │ Runner   │ │ Monitor  │ │ Exporter│ │  │
│  │  │ 爬虫执行 │ │ 状态监控 │ │ 数据导出│ │  │
│  │  └──────────┘ └──────────┘ └─────────┘ │  │
│  └─────────────────────────────────────────┘  │
│                      │                        │
│                      ▼                        │
│  ┌──────────┐  ┌──────────┐                   │
│  │  MySQL   │  │ Scrapling│                   │
│  │ 状态/数据│  │ 爬虫引擎 │                   │
│  └──────────┘  └──────────┘                   │
└──────────────────────────────────────────────┘
```

---

## 目录结构

```
OpenSpider/
├── docs/
│   ├── DESIGN.md                  # 本文档
│   └── API.md                     # API 接口文档
├── openspider/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── cli.py                     # CLI 入口
│   ├── config.py                  # 全局配置（环境变量 / .env）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine.py              # 核心引擎，协调各模块
│   │   ├── registry.py            # 爬虫注册表（热加载）
│   │   ├── runner.py              # 爬虫执行器
│   │   ├── scheduler.py           # 任务调度（APScheduler）
│   │   ├── recovery.py            # 失败检测与恢复
│   │   ├── monitor.py             # 状态监控与统计
│   │   ├── exporter.py            # 数据导出（JSON/JSONL/CSV）
│   │   └── compat.py              # 网站兼容层（编码、ASP/JSP/PHP、SSL）
│   ├── spiders/
│   │   ├── __init__.py            # 自动发现与注册逻辑
│   │   ├── base.py                # 爬虫基类
│   │   └── examples/              # 示例爬虫
│   │       ├── news_spider.py
│   │       └── quotes_spider.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py              # 爬虫管理路由
│   │   ├── schemas.py             # Pydantic 请求/响应模型
│   │   └── deps.py                # 依赖注入
│   ├── models/
│   │   ├── __init__.py
│   │   ├── spider.py              # 爬虫元数据模型
│   │   ├── task.py                # 任务运行记录模型
│   │   └── item.py                # 爬取数据项模型
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py            # MySQL 连接与会话管理
│   │   └── migrations/            # 数据库迁移（Alembic）
│   └── utils/
│       ├── __init__.py
│       ├── logging.py             # 统一日志配置
│       ├── file_watcher.py        # spiders/ 目录文件监控
│       ├── encoding.py            # 编码检测（charset-normalizer）
│       ├── form.py                # HTML 表单字段提取、隐藏字段收集
│       └── url.py                 # URL 规范化、jsessionid 剥离
├── tests/
│   ├── test_registry.py
│   ├── test_runner.py
│   └── test_api.py
├── skill/                         # AI 集成 Skill 描述
│   └── SKILL.md
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 核心模块设计

### 1. 爬虫基类 (`spiders/base.py`)

程序员继承此类编写爬虫，平台通过统一接口管理：

```python
class BaseSpider:
    """爬虫基类，所有爬虫必须继承"""

    name: str                       # 唯一标识，如 "news_spider"
    description: str = ""           # 爬虫描述
    schedule: str | None = None     # cron 表达式，None = 仅手动触发
    max_retries: int = 3            # 失败重试次数
    retry_delay: int = 60           # 重试间隔（秒）
    concurrent_requests: int = 4    # 并发请求数
    download_delay: float = 0.5     # 请求间隔（秒）
    use_stealth: bool = False       # 是否使用隐身模式
    proxies: list[str] = []         # 代理列表

    # === 网站兼容性配置 ===
    encoding: str | None = None     # 强制指定编码，None 则自动检测
    ssl_verify: bool = True         # 是否验证 SSL 证书（老旧站点可能需要关闭）
    follow_redirects: bool = True   # 跟随 HTTP 重定向
    timeout: int = 30               # 请求超时秒数
    default_headers: dict = {}      # 自定义默认请求头
    cookies: dict = {}              # 预设 Cookie

    # === 反爬与指纹配置 ===
    impersonate: str | list[str] = "chrome"  # 浏览器 TLS 指纹伪装（chrome/firefox/safari/edge/tor）
    http3: bool = False             # 使用 HTTP/3 协议
    stealthy_headers: bool = True   # 生成真实浏览器请求头
    block_ads: bool = False         # 屏蔽 3500+ 广告/追踪域名
    blocked_domains: set[str] = set()  # 自定义屏蔽域名列表
    dns_over_https: bool = False    # 通过 Cloudflare DoH 防止 DNS 泄露
    locale: str | None = None       # 浏览器语言（如 en-US、zh-CN）
    timezone_id: str | None = None  # 浏览器时区（如 Asia/Shanghai）

    # === 浏览器高级配置（use_stealth=True 时生效） ===
    solve_cloudflare: bool = False  # 自动破解 Cloudflare Turnstile/Interstitial
    block_webrtc: bool = False      # 阻断 WebRTC 防止真实 IP 泄露
    hide_canvas: bool = False       # Canvas 操作加噪防止指纹追踪
    allow_webgl: bool = True        # 是否允许 WebGL（禁用可降低指纹特征）
    real_chrome: bool = False       # 使用设备上真实 Chrome 而非 Chromium
    cdp_url: str | None = None      # CDP 远程浏览器地址（如 ws://host:9222）
    user_data_dir: str | None = None  # 浏览器用户数据目录（持久化 Cookie/LocalStorage）
    init_script: str | None = None  # 页面创建前注入的 JS 文件路径
    max_pages: int = 1              # 浏览器标签页池大小（并发抓取页面数）
    disable_resources: bool = True  # 屏蔽字体/图片/媒体等非必要资源加载
    network_idle: bool = False      # 等待网络空闲（无连接 500ms）再返回
    load_dom: bool = True           # 等待 DOM 加载完成（domcontentloaded）
    wait_selector: str | None = None  # 等待指定 CSS 选择器出现
    wait_selector_state: str = "attached"  # 等待状态（attached/detached/visible/hidden）
    wait: int = 0                   # 页面加载后额外等待毫秒数
    page_action: Callable | None = None  # 页面加载后执行的 Playwright 自动化操作
    page_setup: Callable | None = None   # 页面导航前执行的 Playwright 设置操作
    capture_xhr: str | None = None  # XHR/Fetch 拦截的 URL 正则（捕获 SPA API 响应）

    # === 自适应爬取配置 ===
    adaptive: bool = False          # 启用自适应选择器（网站改版后自动定位元素）
    adaptive_storage: str | None = None  # 自适应数据库路径（默认 SQLite）

    async def run(self) -> AsyncGenerator[dict, None]:
        """核心爬取逻辑，yield 爬取的数据项。

        在 run() 内部通过 self 发起请求：
          - await self.get(url)           → HTTP GET，返回 Response
          - await self.post(url, data=)   → HTTP POST，返回 Response
          - self.session                  → 当前 Scrapling session 实例，可直接调用底层方法
          - self.should_stop              → bool，检查是否收到停止信号，用于优雅退出循环

        示例：
            async def run(self):
                page = await self.get("https://example.com")
                for item in page.css(".article"):
                    if self.should_stop:
                        break
                    yield {"title": item.css("h2::text").get("")}
        """
        raise NotImplementedError

    async def on_start(self, resuming: bool = False):
        """启动前钩子，resuming=True 表示从断点恢复"""
        pass

    async def on_error(self, error: Exception):
        """出错时钩子"""
        pass

    async def on_complete(self):
        """完成时钩子"""
        pass

    async def on_item_scraped(self, item: dict) -> dict | None:
        """每条数据项的后处理，返回 None 则丢弃"""
        return item
```

### 2. 爬虫注册表 (`core/registry.py`)

负责爬虫的发现、注册、热加载：

- **启动时扫描** `spiders/` 目录，自动导入所有继承 `BaseSpider` 的类并注册
- **文件监控**：用 `watchdog` 监控 `spiders/` 目录，新增/修改文件时自动重新加载
- **运行时注册**：支持通过 API 上传 `.py` 文件动态注册
- **注册表存储**：爬虫元数据（name、description、schedule 等）写入 MySQL，运行状态以注册表为准

```
注册流程：
  文件写入 spiders/ → watchdog 检测 → importlib 动态导入
  → 验证继承 BaseSpider → 注册到内存表 + 写入 MySQL
```

**爬虫文件校验**（API 上传和热加载均执行）：
1. **语法检查**：`compile()` 编译源码，语法错误直接拒绝并返回错误信息
2. **接口检查**：动态导入后检查是否继承 `BaseSpider`，是否有 `name` 和 `run()` 方法
3. **name 唯一性**：检查 `name` 是否与已注册爬虫冲突，冲突则拒绝（除非明确覆盖）
4. **沙箱限制**（可选）：禁止 `os.system`、`subprocess`、`eval` 等危险调用，防止恶意代码

### 3. 爬虫执行器 (`core/runner.py`)

负责单个爬虫的执行生命周期。Runner 不动态生成 Scrapling 子类，而是为 BaseSpider 实例注入 Scrapling 的 session 能力：

- 创建 Scrapling 的 `FetcherSession` / `AsyncDynamicSession` / `AsyncStealthySession`（根据爬虫配置自动选择）
- 将 session 绑定到爬虫实例的 `self.session`，供 `run()` 内部通过 `self.get()` / `self.post()` 调用
- 管理 `crawldir` 目录用于暂停恢复
- 采集运行统计数据（请求数、成功数、失败数、耗时）
- 将爬取的数据项通过 `on_item_scraped` 管道处理后写入 MySQL

**停止信号机制**：

Runner 通过 `asyncio.Event` 实现优雅停止：
1. 调用 `stop()` 设置 `_stop_event`
2. 爬虫在 `run()` 循环中检查 `self.should_stop`（内部读取 `_stop_event`）
3. 收到信号后 `run()` 退出循环，执行 `on_complete()` 钩子，保存断点
4. 若 `run()` 长时间不响应（超过 30 秒），Runner 强制取消协程

```
执行流程：
  Runner.start(spider_name)
  → 从 Registry 获取爬虫实例
  → 根据配置创建 Scrapling session（HTTP/Dynamic/Stealthy）
  → 将 session 注入爬虫实例
  → 调用 spider.on_start()
  → 执行 spider.run()，收集 yield 的数据项
  → 每条数据经 on_item_scraped 处理
  → 写入 MySQL items 表
  → 运行结束调用 spider.on_complete()
  → 关闭 session
  → 更新任务状态为 completed

停止流程：
  Runner.stop(spider_name)
  → 设置 _stop_event
  → 爬虫 run() 检测到 should_stop=True，退出循环
  → 保存 Scrapling crawldir 断点
  → 更新任务状态为 paused（可恢复）或 stopped
  → 超时 30s 未退出则强制取消
```

### 4. 任务调度器 (`core/scheduler.py`)

基于 APScheduler，支持：

- **定时任务**：读取爬虫的 `schedule` 字段（cron 表达式），自动注册定时触发
- **手动触发**：API/CLI 调用立即启动
- **单例保护**：同一爬虫同一时间只能有一个实例在运行
- **动态更新**：爬虫重新注册时自动更新调度计划

### 5. 失败恢复 (`core/recovery.py`)

- **运行时重试**：爬虫执行过程中抛异常，按 `max_retries` × `retry_delay` 自动重试
- **指数退避**：连续失败时退避间隔翻倍，上限 1 小时
- **崩溃恢复**：平台重启后，检查 MySQL 中状态为 `running` 的任务，标记为 `crashed`，根据配置决定是否自动重启
- **断点续爬**：利用 Scrapling 的 `crawldir` 机制，暂停/崩溃后恢复从断点继续

### 6. 数据导出 (`core/exporter.py`)

- 从 MySQL 读取爬取数据，支持导出为 JSON、JSONL、CSV
- 支持按爬虫名称、时间范围筛选
- 支持流式导出（大数据量时不占满内存）

### 7. 网站兼容层 (`core/compat.py`)

平台需要能爬取所有类型的网站，包括老旧的 ASP、JSP、PHP 站点。兼容层封装了针对不同技术栈的特殊处理逻辑，爬虫基类提供配置项，Runner 执行时自动应用。

#### 7.1 编码处理

老旧站点（特别是中文、日文站点）常用非 UTF-8 编码，必须正确处理：

- **自动检测**：使用 `charset-normalizer` 库检测响应编码，优先读取 HTTP Content-Type 头中的 charset，其次分析 HTML meta 标签，最后用统计模型推断
- **手动指定**：爬虫通过 `encoding` 字段强制指定编码（如 `gbk`、`gb2312`、`big5`、`shift_jis`、`euc-kr`）
- **统一输出**：所有文本内容统一转为 UTF-8 存储

```
编码检测优先级：
  1. BaseSpider.encoding（手动指定，最高优先级）
  2. HTTP Content-Type: text/html; charset=gbk
  3. HTML <meta charset="gbk"> 或 <meta http-equiv="Content-Type" content="...; charset=gbk">
  4. charset-normalizer 统计推断
  5. 回退 UTF-8
```

#### 7.2 ASP.NET 站点支持

ASP.NET WebForms 站点有特殊的表单提交机制，需要特殊处理：

- **ViewState**：页面中 `__VIEWSTATE`、`__VIEWSTATEGENERATOR`、`__EVENTVALIDATION` 等隐藏字段必须在 POST 请求中携带
- **PostBack 机制**：ASP.NET 的按钮点击本质是表单 POST，需要提取表单所有隐藏字段一并提交
- **EventTarget**：`__EVENTTARGET` 字段标识触发事件的控件
- **Session Cookie**：`ASP.NET_SessionId` 必须在请求间保持

爬虫基类提供辅助方法：

```python
class BaseSpider:
    def extract_asp_form(self, response, form_selector="form") -> dict:
        """提取 ASP.NET 表单的所有隐藏字段（ViewState 等）"""
        ...

    def build_asp_post(self, form_fields: dict, **extra) -> dict:
        """构建 ASP.NET POST 请求体，合并隐藏字段与用户数据"""
        ...
```

#### 7.3 JSP/Servlet 站点支持

Java Web 站点的特殊行为：

- **JSESSIONID**：Servlet 容器通过 URL 重写传递 Session ID（如 `page.jsp;jsessionid=ABC123`），需要从 URL 中提取并在后续请求中携带
- **表单认证**：JSP 站点常用 `j_security_check` 表单登录，需要 POST 用户名密码并保持 Session
- **Token 机制**：部分站点在表单中嵌入 CSRF token（如 Struts 的 `token`、Spring 的 `_csrf`），需要提取并回传
- **URL 重写**：`;jsessionid=...` 后缀需要自动剥离并转为 Cookie

辅助方法：

```python
class BaseSpider:
    def extract_jsp_session(self, url: str) -> str | None:
        """从 URL 中提取 jsessionid"""
        ...

    def extract_csrf_token(self, response, selector="input[name='_csrf']") -> str | None:
        """提取 CSRF token"""
        ...
```

#### 7.4 PHP 老旧站点支持

- **PHPSESSID**：PHP 默认 Session Cookie 名称，需要跨请求保持
- **表单 token**：PHP 站点常用 `$_SESSION['token']` 做 CSRF 防护
- **序列化格式**：部分老 PHP 站点返回 `serialize()` 格式数据而非 JSON，需要反序列化处理
- **编码混乱**：老 PHP 站点可能混用 UTF-8 和 GBK，需要逐段检测

#### 7.5 老旧 SSL/TLS 支持

很多老旧站点使用过期或自签名 SSL 证书，或仅支持旧版 TLS：

- **证书跳过**：`ssl_verify=False` 跳过证书验证（爬虫配置项）
- **TLS 降级**：自动协商到服务器支持的最高 TLS 版本
- **自签名证书**：支持指定 CA 证书文件路径

#### 7.6 HTTP 协议兼容

老旧 Web 服务器可能不完全支持 HTTP/1.1：

- **HTTP/1.0 回退**：部分老服务器不支持 HTTP/1.1 的 `Host` 头或 chunked 传输，自动回退到 HTTP/1.0
- **Keep-Alive**：老服务器的 Keep-Alive 行为不一致，可配置禁用
- **重定向处理**：老旧站点可能用 `<meta http-equiv="refresh">` 或 JavaScript 做跳转，而非标准 HTTP 301/302，需要在解析层检测并处理

#### 7.7 Frame/Iframe 处理

2000 年代的站点大量使用 `<frameset>` 和 `<frame>`：

- **Frame 检测**：解析器检测页面是否为 frameset，自动提取各 frame 的 URL
- **内容合并**：将多个 frame 的内容合并为一个逻辑页面供选择器使用
- **Iframe 提取**：自动识别 iframe 内容并提供访问入口

辅助方法：

```python
class BaseSpider:
    def extract_frames(self, response) -> list[str]:
        """提取页面中所有 frame/iframe 的 URL"""
        ...

    async def fetch_frame(self, frame_url: str, sid: str = "") -> Response:
        """获取单个 frame 的内容"""
        ...
```

#### 7.8 表单提交辅助

不同类型站点的表单提交统一抽象：

```python
class BaseSpider:
    def auto_fill_form(self, response, form_selector: str, data: dict) -> dict:
        """自动提取表单所有字段（含隐藏字段），合并用户数据，返回完整 POST body"""
        # 1. 解析表单所有 input/select/textarea
        # 2. 提取隐藏字段（ViewState、CSRF token 等）
        # 3. 合并用户传入的 data（覆盖默认值）
        # 4. 处理 checkbox、radio、select 的值
        # 5. 返回完整的 form data dict
        ...
```

#### 7.9 自适应爬取（Adaptive Scraping）

网站改版后选择器失效是爬虫最常见的维护成本。Scrapling 的自适应功能可以自动定位改版后的元素：

- **首次保存**：用 `auto_save=True` 选择元素时，自动保存元素的唯一属性（tag、text、attributes、siblings、path、parent 信息）到数据库
- **改版后定位**：用 `adaptive=True` 选择时，Scrapling 从数据库取回属性，在页面上找相似度最高的元素
- **存储隔离**：按域名隔离存储，不同网站的自适应数据互不干扰
- **adaptive_domain**：当网站域名变更时，可指定新旧域名共享自适应数据

```python
class BaseSpider:
    def select(self, response, selector: str, css: bool = True, adaptive: bool = False, auto_save: bool = False):
        """统一选择器方法，自动应用自适应配置"""
        ...

    def save_element(self, response, element, identifier: str):
        """手动保存元素的自适应数据"""
        ...

    def find_similar(self, response, element, similarity_threshold: float = 0.2, ignore_attributes: list[str] = ['href', 'src']):
        """查找页面上与给定元素结构相似的所有元素"""
        ...
```

#### 7.10 增强元素查找

除 CSS/XPath 选择器外，提供更灵活的元素查找方式：

```python
class BaseSpider:
    def find_by_text(self, response, text: str, tag: str | None = None, partial: bool = False,
                     case_sensitive: bool = False, first_match: bool = True):
        """按文本内容查找元素，支持精确/模糊/大小写控制"""
        ...

    def find_by_regex(self, response, pattern: str | re.Pattern, first_match: bool = True):
        """按正则表达式匹配元素文本内容"""
        ...

    def generate_selector(self, element, css: bool = True, full: bool = False) -> str:
        """为任意元素自动生成 CSS 或 XPath 选择器（用于调试或 AI 生成爬虫）"""
        ...
```

#### 7.11 XHR/Fetch 拦截

SPA（单页应用）通过 AJAX 加载数据，直接爬取页面拿不到内容。XHR 拦截可以在浏览器加载页面时捕获后台 API 响应：

- **capture_xhr**：传入 URL 正则表达式，匹配的 XHR/Fetch 响应会被捕获
- **捕获结果**：每个 XHR 响应是完整的 Response 对象（url、status、headers、body）
- **典型场景**：Vue/React 应用的数据接口、分页 API、搜索接口

```python
class BaseSpider:
    # 爬虫配置
    capture_xhr: str | None = r"https://api\.example\.com/.*"  # 拦截匹配的 API 请求

    async def run(self):
        page = await self.get("https://spa-site.com")
        # 直接访问捕获的 XHR 响应
        for xhr in page.captured_xhr:
            data = xhr.json()  # 已经是结构化数据，不需要解析 HTML
            yield data
```

#### 7.12 浏览器自动化

对于需要交互的页面（点击按钮、滚动加载、填写表单），通过 Playwright 的 Page API 实现：

```python
from playwright.async_api import Page

class BaseSpider:
    async def run(self):
        # page_action: 页面加载后执行（滚动、点击、等待等）
        async def scroll_and_click(page: Page):
            await page.mouse.wheel(0, 500)           # 向下滚动
            await page.click("button.load-more")      # 点击加载更多
            await page.wait_for_timeout(2000)          # 等待 2 秒

        page = await self.get("https://infinite-scroll.com", page_action=scroll_and_click)
        yield {"content": page.css(".item").getall()}
```

#### 7.13 浏览器指纹控制

高级反爬场景需要精细控制浏览器指纹，避免被检测为自动化工具：

| 功能 | 配置项 | 说明 |
|------|--------|------|
| WebRTC 阻断 | `block_webrtc=True` | 防止 WebRTC 泄露真实 IP（即使使用了代理） |
| Canvas 噪声 | `hide_canvas=True` | 对 Canvas 操作添加随机噪声，防止画布指纹追踪 |
| WebGL 控制 | `allow_webgl=False` | 禁用 WebGL 降低指纹特征（但部分 WAF 会检测 WebGL 是否启用） |
| 真实 Chrome | `real_chrome=True` | 使用设备上安装的 Chrome 而非 Chromium，指纹更真实 |
| 语言伪装 | `locale="zh-CN"` | 修改 navigator.language 和 Accept-Language 头 |
| 时区伪装 | `timezone_id="Asia/Shanghai"` | 修改浏览器时区，防止时区不匹配检测 |
| JS 注入 | `init_script="/path/to/hook.js"` | 页面创建前注入 JS，可用于注入自定义 hook |

#### 7.14 Cloudflare 自动破解

`StealthyFetcher` 内置 Cloudflare 挑战破解，无需第三方服务：

- **JavaScript 挑战**：自动执行 CF 的 JS 验证
- **交互式挑战**：自动点击验证框
- **隐形挑战**：自动完成后台静默验证
- **自定义验证码**：处理嵌入式 reCAPTCHA 等

配置：`solve_cloudflare=True`，建议配合 `timeout=60000`（60 秒）给足破解时间。

#### 7.15 CDP 远程浏览器连接

分布式场景下，多个爬虫节点可共享一个浏览器实例：

- **cdp_url**：通过 Chrome DevTools Protocol 连接远程浏览器（如 `ws://browser-server:9222`）
- **用途**：减少浏览器启动开销、共享浏览器指纹、连接已有浏览器会话

#### 7.16 浏览器标签页池

`max_pages` 参数启用标签页池，并发抓取多个页面：

- 每个请求分配一个标签页，完成后关闭
- 池内标签页数量不超过 `max_pages`
- 超出时自动等待空闲标签页（60 秒超时）
- 适用于需要浏览器但想并发的场景

#### 7.17 响应元数据

爬虫在 `run()` 中通过 `self.get()` 获取的 Response 对象包含丰富的元数据：

```python
class BaseSpider:
    async def run(self):
        page = await self.get("https://example.com")

        # HTTP 元数据
        page.status           # HTTP 状态码
        page.reason           # 状态消息
        page.headers          # 响应头
        page.request_headers  # 请求头
        page.cookies          # 响应 Cookie（dict）
        page.history          # 重定向历史
        page.body             # 原始响应体（bytes）
        page.encoding         # 响应编码
        page.meta             # 元数据字典（如使用的代理）

        # XHR 捕获结果
        page.captured_xhr     # 捕获的 XHR 响应列表
```

#### 7.18 广告与追踪器屏蔽

- **block_ads**：屏蔽 3500+ 已知广告/追踪域名，节省流量和代理用量
- **blocked_domains**：自定义屏蔽域名列表（支持子域名匹配）
- 两者可叠加使用

#### 7.19 DNS over HTTPS

代理场景下，DNS 查询可能绕过代理直接发出，泄露真实访问目标：

- **dns_over_https=True**：通过 Cloudflare 的 DoH 服务路由 DNS 查询
- 防止 DNS 泄露，增强代理匿名性

#### 7.20 User Data Dir 持久化

指定浏览器用户数据目录，持久化 Cookie、LocalStorage、SessionStorage：

- **user_data_dir**：指定目录路径，浏览器会话数据自动保存
- **用途**：跨爬虫运行保持登录状态、减少重复登录请求
- **注意**：仅在 Session 模式下有效

---

### 8. 模板爬虫

基于 Scrapling 的 `CrawlSpider`、`SitemapSpider`、`LinkExtractor`，平台内置常用爬虫模板，程序员可直接继承使用，减少重复代码。

#### 8.1 规则爬虫（RuleSpider）

继承 Scrapling 的 `CrawlSpider`，通过声明式规则自动跟进链接：

```python
class RuleSpider(BaseSpider):
    """规则驱动爬虫，通过 rules() 声明链接跟进规则"""

    def rules(self) -> list[CrawlRule]:
        """返回规则列表，每条规则包含 LinkExtractor + 回调"""
        raise NotImplementedError

    async def run(self):
        """默认实现：使用 Scrapling CrawlSpider 引擎执行规则"""
        ...
```

示例用法：

```python
class BlogCrawler(RuleSpider):
    name = "blog_crawler"
    start_urls = ["https://example.com"]

    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
            CrawlRule(LinkExtractor(allow=r"/page/\d+/")),  # 只跟进，不解析
        ]

    async def parse_post(self, response):
        yield {"title": response.css("h1::text").get(), "url": response.url}
```

LinkExtractor 支持的过滤参数：

| 参数 | 说明 |
|------|------|
| `allow` | URL 正则白名单 |
| `deny` | URL 正则黑名单（优先于 allow） |
| `allow_domains` | 域名白名单（自动匹配子域名） |
| `deny_domains` | 域名黑名单 |
| `restrict_css` / `restrict_xpath` | 限制从页面的哪个区域提取链接 |
| `tags` | 提取链接的标签（默认 a、area） |
| `attrs` | 提取链接的属性（默认 href） |
| `deny_extensions` | 排除的文件扩展名（pdf、zip、图片等） |
| `canonicalize` | 规范化 URL（排序参数、标准化路径） |

#### 8.2 Sitemap 爬虫（SitemapRuleSpider）

继承 Scrapling 的 `SitemapSpider`，从 sitemap.xml 驱动爬取：

```python
class SitemapRuleSpider(BaseSpider):
    """Sitemap 驱动爬虫，从 sitemap.xml 提取 URL 并按规则分发"""

    sitemap_urls: list[str] = []         # sitemap URL 列表
    sitemap_follow: LinkExtractor | None = None  # 过滤要跟进的子 sitemap
    sitemap_alternate_links: bool = False  # 是否提取多语言 alternate 链接

    def rules(self) -> list[CrawlRule]:
        """返回规则列表"""
        raise NotImplementedError
```

示例用法：

```python
class ProductSitemap(SitemapRuleSpider):
    name = "product_sitemap"
    sitemap_urls = ["https://shop.example.com/sitemap.xml"]

    def rules(self):
        return [
            CrawlRule(LinkExtractor(allow=r"/products/"), callback=self.parse_product),
            CrawlRule(LinkExtractor(allow=r"/categories/"), callback=self.parse_category),
        ]

    async def parse_product(self, response):
        yield {
            "name": response.css("h1::text").get(),
            "price": response.css(".price::text").get(),
        }
```

支持从 `robots.txt` 自动提取 Sitemap 指令：

```python
sitemap_urls = ["https://example.com/robots.txt"]  # 自动解析 Sitemap: 行
```

#### 8.3 自定义链接提取

不使用模板爬虫时，也可在普通 BaseSpider 中使用 LinkExtractor：

```python
class MySpider(BaseSpider):
    name = "custom"
    start_urls = ["https://example.com"]

    async def run(self):
        links = LinkExtractor(allow=r"/posts/", deny_domains="ads.example.com")
        page = await self.get("https://example.com")
        for url in links.extract(page.response):
            yield response.follow(url, callback=self.parse_post)
```

---

### 10. 辅助工具 (`utils/`)

- **编码检测** (`utils/encoding.py`)：封装 charset-normalizer，提供 `detect_encoding(raw_bytes, declared_charset)` 函数
- **表单解析** (`utils/form.py`)：HTML 表单字段提取、隐藏字段收集、multipart 编码
- **URL 处理** (`utils/url.py`)：相对 URL 拼接、jsessionid 剥离、URL 规范化、LinkExtractor 集成
- **选择器生成** (`utils/selector.py`)：为任意元素生成 CSS/XPath 选择器（用于调试和 AI 生成爬虫）

---

## 数据模型（MySQL）

### 表 `spiders` — 爬虫注册信息

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| name | VARCHAR(128) UNIQUE | 爬虫唯一标识 |
| description | TEXT | 爬虫描述 |
| file_path | VARCHAR(512) | 爬虫文件路径 |
| schedule | VARCHAR(64) | cron 表达式，NULL 表示手动 |
| max_retries | INT | 最大重试次数 |
| retry_delay | INT | 重试间隔秒数 |
| config | JSON | 爬虫自定义配置 |
| status | ENUM('idle','running','paused','failed','disabled') | 当前状态 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 表 `tasks` — 任务运行记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| spider_name | VARCHAR(128) FK | 关联爬虫 |
| status | ENUM('pending','running','completed','failed','paused','crashed') | 任务状态 |
| started_at | DATETIME | 启动时间 |
| finished_at | DATETIME | 结束时间 |
| items_scraped | INT | 已爬取条数 |
| requests_made | INT | 请求数 |
| errors_count | INT | 错误数 |
| retry_count | INT | 已重试次数 |
| error_message | TEXT | 最后一次错误信息 |
| crawldir | VARCHAR(512) | Scrapling 断点目录 |
| executor_node | VARCHAR(128) | 执行节点标识（分布式模式），单机为 NULL |
| created_at | DATETIME | 创建时间 |

### 表 `items` — 爬取数据

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| spider_name | VARCHAR(128) | 来源爬虫 |
| task_id | BIGINT FK | 关联任务 |
| data | JSON | 爬取的数据内容 |
| url | VARCHAR(2048) | 来源 URL |
| crawled_at | DATETIME | 爬取时间 |

索引：
- `idx_items_spider_name` ON (spider_name)
- `idx_items_task_id` ON (task_id)
- `idx_items_crawled_at` ON (crawled_at)
- `idx_items_spider_crawled` ON (spider_name, crawled_at) — 常用组合查询

### 表 `logs` — 运行日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| spider_name | VARCHAR(128) | 爬虫名称 |
| task_id | BIGINT FK | 关联任务 |
| level | ENUM('debug','info','warning','error') | 日志级别 |
| message | TEXT | 日志内容 |
| created_at | DATETIME | 创建时间 |

---

## API 接口设计

### 爬虫管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/spiders` | 列出所有爬虫及状态 |
| GET | `/spiders/{name}` | 获取单个爬虫详情 |
| POST | `/spiders/{name}/start` | 启动爬虫 |
| POST | `/spiders/{name}/stop` | 停止爬虫 |
| POST | `/spiders/{name}/pause` | 暂停爬虫 |
| POST | `/spiders/{name}/resume` | 恢复爬虫 |
| DELETE | `/spiders/{name}` | 删除爬虫（先停止） |
| POST | `/spiders/upload` | 上传爬虫文件（.py），自动校验语法和接口合规性 |

### 任务查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 任务列表（支持按爬虫、状态筛选） |
| GET | `/tasks/{id}` | 任务详情 |
| GET | `/tasks/{id}/logs` | 任务日志 |

### 数据查询与导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/items` | 爬取数据查询（分页、筛选） |
| GET | `/export/{spider_name}` | 导出数据（format=json/jsonl/csv） |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（返回服务状态、MySQL 连接、活跃爬虫数） |

### 能力描述（给 AI 用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/capabilities` | 返回平台能力、爬虫接口规范、示例代码 |

`/capabilities` 返回内容示例：

```json
{
  "platform": "OpenSpider",
  "version": "0.1.0",
  "spider_interface": {
    "base_class": "openspider.spiders.base.BaseSpider",
    "required_attributes": ["name"],
    "optional_attributes": [
      "description", "schedule", "max_retries", "retry_delay",
      "concurrent_requests", "download_delay", "use_stealth", "proxies",
      "encoding", "ssl_verify", "follow_redirects", "timeout", "default_headers", "cookies",
      "impersonate", "http3", "stealthy_headers", "block_ads", "blocked_domains",
      "dns_over_https", "locale", "timezone_id",
      "solve_cloudflare", "block_webrtc", "hide_canvas", "allow_webgl",
      "real_chrome", "cdp_url", "user_data_dir", "init_script", "max_pages",
      "disable_resources", "network_idle", "load_dom",
      "wait_selector", "wait_selector_state", "wait",
      "page_action", "page_setup", "capture_xhr",
      "adaptive", "adaptive_storage"
    ],
    "required_methods": ["run() -> AsyncGenerator[dict, None]"],
    "optional_hooks": ["on_start", "on_error", "on_complete", "on_item_scraped"],
    "helper_methods": [
      "get(url, **kwargs) -> Response", "post(url, **kwargs) -> Response",
      "find_by_text(response, text, **kwargs)", "find_by_regex(response, pattern, **kwargs)",
      "find_similar(response, element, **kwargs)",
      "auto_fill_form(response, selector, data) -> dict",
      "extract_asp_form(response, selector) -> dict",
      "extract_jsp_session(url) -> str", "extract_csrf_token(response, selector) -> str",
      "extract_frames(response) -> list[str]", "generate_selector(element, css=True) -> str"
    ],
    "template_spiders": ["RuleSpider", "SitemapRuleSpider"],
    "example_code": "class MySpider(BaseSpider):\n    name = 'my_spider'\n    start_urls = ['https://example.com']\n    use_stealth = True\n    solve_cloudflare = True\n    block_ads = True\n    adaptive = True\n    async def run(self):\n        page = await self.get(self.start_urls[0])\n        for item in page.css('.article'):\n            yield {'title': item.css('h2::text').get('')}"
  },
  "api_docs": "/docs",
  "supported_export_formats": ["json", "jsonl", "csv"]
}
```

---

## CLI 设计

```bash
# 启动平台（API 服务 + 调度器 + 文件监控）
openspider serve

# 爬虫管理
openspider list                          # 列出所有爬虫
openspider start <name>                  # 启动
openspider stop <name>                   # 停止
openspider pause <name>                  # 暂停
openspider resume <name>                 # 恢复
openspider info <name>                   # 查看详情

# 任务查看
openspider tasks                         # 任务列表
openspider tasks --spider <name>         # 按爬虫筛选
openspider logs <task_id>                # 查看任务日志

# 数据操作
openspider export <name> --format json   # 导出数据
openspider items <name> --limit 100      # 预览数据

# 爬虫文件操作
openspider add <file.py>                 # 上传注册新爬虫
openspider remove <name>                 # 移除爬虫
openspider validate <file.py>            # 验证爬虫文件是否合法
```

---

## 配置（.env）

```env
# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=openspider

# 服务
API_HOST=0.0.0.0
API_PORT=8000

# 爬虫
SPIDERS_DIR=./openspider/spiders
CRAWL_DATA_DIR=./crawl_data
MAX_CONCURRENT_SPIDERS=10

# 日志
LOG_LEVEL=INFO
LOG_FILE=./logs/openspider.log
```

---

## 分布式方案

单机模式下所有组件跑在一个进程内。分布式模式的扩展思路：

- **API 层**：多个 API 实例，前面挂 Nginx 负载均衡
- **任务调度**：用 MySQL 分布式锁保证同一爬虫只有一个实例执行
- **爬虫执行**：不同节点可以跑不同爬虫，通过 MySQL 协调状态
- **文件同步**：spiders/ 目录通过 Git 或共享存储同步

分布式核心靠 MySQL 做状态协调，不需要额外的消息队列。任务表加 `executor_node` 字段记录执行节点，通过 `SELECT ... FOR UPDATE` 抢占任务。

---

## AI 集成方式（Skill）

平台暴露标准化接口，外部 AI 通过以下流程集成：

1. **GET /capabilities** — AI 获取平台能力描述和爬虫接口规范
2. **分析目标网站** — AI 自行完成（fetch + 分析 HTML 结构）
3. **生成爬虫代码** — AI 按 BaseSpider 接口规范生成 `.py` 文件
4. **POST /spiders/upload** — 上传爬虫文件到平台
5. **POST /spiders/{name}/start** — 启动爬虫
6. **GET /items?spider={name}** — 获取爬取结果
7. **GET /tasks/{id}** — 查看运行状态和错误

AI 侧需要的 Skill 描述见 `skill/SKILL.md`，包含完整的接口文档、爬虫接口规范、示例代码，供 AI 理解平台能力并正确调用。

---

## 技术选型

| 组件 | 选择 | 版本 | 理由 |
|------|------|------|------|
| 爬虫引擎 | Scrapling | >=0.4.8 | 自带暂停恢复、代理轮换、反爬绕过 |
| API 框架 | FastAPI | >=0.110 | 异步原生，自动生成 OpenAPI 文档 |
| 任务调度 | APScheduler | >=3.10 | 支持 cron，可嵌入，轻量 |
| 数据库 | MySQL | >=8.0 | 用户指定 |
| ORM | SQLAlchemy | >=2.0 | 成熟、异步支持好 |
| 迁移 | Alembic | >=1.13 | SQLAlchemy 配套 |
| 文件监控 | watchdog | >=3.0 | 跨平台文件系统监控 |
| CLI | Click | >=8.0 | 成熟、简洁 |
| 编码检测 | charset-normalizer | >=3.0 | 自动检测响应编码，支持中日韩等多字节编码 |
| 日志 | loguru | >=0.7 | 比标准库好用，结构化日志 |

---

## 实施阶段

### Phase 1 — 核心骨架
- 项目结构搭建、配置、MySQL 连接
- BaseSpider 基类（含基础配置项：encoding、ssl_verify、timeout 等）
- Registry 注册表 + 文件热加载 + 爬虫文件校验
- Runner 执行器（session 注入、停止信号机制、should_stop）
- 基础 API（爬虫列表、启停、状态查询、/health）

### Phase 2 — HTTP 请求与会话管理
- FetcherSession 集成（self.get / self.post）
- 浏览器 TLS 指纹伪装（impersonate）
- 代理轮换（ProxyRotator）
- 会话自动选择（HTTP / Dynamic / Stealthy 根据配置自动切换）
- 响应元数据暴露（status、headers、cookies、body、meta）

### Phase 3 — 调度与恢复
- APScheduler 定时任务
- 失败重试与指数退避
- 崩溃恢复
- 暂停/断点续爬（Scrapling crawldir）

### Phase 4 — 网站兼容层
- 编码自动检测（charset-normalizer）
- ASP.NET 表单辅助（ViewState、PostBack）
- JSP/Servlet 支持（JSESSIONID、CSRF token）
- PHP 站点支持（PHPSESSID、序列化格式）
- 表单自动填充（auto_fill_form）
- Frame/Iframe 处理
- HTTP 协议兼容（HTTP/1.0 回退、meta refresh 检测）

### Phase 5 — 反爬与浏览器功能
- Cloudflare 自动破解（solve_cloudflare）
- 浏览器指纹控制（WebRTC 阻断、Canvas 噪声、WebGL 控制）
- 广告/追踪器屏蔽（block_ads、blocked_domains）
- DNS over HTTPS（dns_over_https）
- Real Chrome 模式
- CDP 远程浏览器连接
- HTTP/3 支持
- Locale/Timezone 伪装
- Init Script 注入
- User Data Dir 持久化
- 浏览器标签页池（max_pages）

### Phase 6 — 增强解析与模板爬虫
- 自适应爬取（adaptive scraping）
- 增强元素查找（find_by_text、find_by_regex、find_similar）
- 选择器自动生成（generate_selector）
- XHR/Fetch 拦截（capture_xhr）
- 浏览器自动化（page_action、page_setup）
- RuleSpider 模板（CrawlSpider + LinkExtractor + rules）
- SitemapRuleSpider 模板（SitemapSpider + sitemap_urls）
- LinkExtractor 直接使用

### Phase 7 — 数据与导出
- items 表写入与查询
- 数据导出（JSON/JSONL/CSV）
- /capabilities 接口

### Phase 8 — CLI 与 Skill
- CLI 完整实现
- Skill 描述文档（SKILL.md）
- 示例爬虫（新闻、电商、SPA、受保护站点）
- README

### Phase 9 — 分布式支持
- MySQL 分布式锁
- 多节点状态协调
- executor_node 路由
- CDP 远程浏览器共享
