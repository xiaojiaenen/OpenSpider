"""爬虫基类，所有爬虫必须继承"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapling.operators import Response


class BaseSpider:
    """爬虫基类

    程序员继承此类编写爬虫，平台通过统一接口管理。
    在 run() 内部通过 self.get()/self.post() 发起请求。
    """

    # === 基本信息 ===
    name: str = ""                       # 唯一标识，如 "news_spider"
    description: str = ""                # 爬虫描述
    start_urls: list[str] = []           # 入口 URL 列表
    schedule: str | None = None          # cron 表达式，None = 仅手动触发
    max_retries: int = 3                 # 失败重试次数
    retry_delay: int = 60                # 重试间隔（秒）
    concurrent_requests: int = 4         # 并发请求数
    download_delay: float = 0.5          # 请求间隔（秒）
    use_stealth: bool = False            # 是否使用隐身模式
    proxies: list[str] = []              # 代理列表

    # === 网站兼容性配置 ===
    encoding: str | None = None          # 强制指定编码，None 则自动检测
    ssl_verify: bool = True              # 是否验证 SSL 证书
    follow_redirects: bool = True        # 跟随 HTTP 重定向
    timeout: int = 30                    # 请求超时秒数
    default_headers: dict = {}           # 自定义默认请求头
    cookies: dict = {}                   # 预设 Cookie

    # === 反爬与指纹配置 ===
    impersonate: str | list[str] = "chrome"  # 浏览器 TLS 指纹伪装
    http3: bool = False                  # 使用 HTTP/3 协议
    stealthy_headers: bool = True        # 生成真实浏览器请求头
    block_ads: bool = False              # 屏蔽广告/追踪域名
    blocked_domains: set[str] = set()    # 自定义屏蔽域名
    dns_over_https: bool = False         # 防止 DNS 泄露
    locale: str | None = None            # 浏览器语言
    timezone_id: str | None = None       # 浏览器时区

    # === 浏览器高级配置（use_stealth=True 时生效） ===
    solve_cloudflare: bool = False       # 自动破解 Cloudflare
    block_webrtc: bool = False           # 阻断 WebRTC
    hide_canvas: bool = False            # Canvas 噪声
    allow_webgl: bool = True             # 允许 WebGL
    real_chrome: bool = False            # 使用真实 Chrome
    cdp_url: str | None = None           # CDP 远程浏览器地址
    user_data_dir: str | None = None     # 浏览器用户数据目录
    init_script: str | None = None       # 页面创建前注入的 JS 文件
    max_pages: int = 1                   # 浏览器标签页池大小
    disable_resources: bool = True       # 屏蔽非必要资源
    network_idle: bool = False           # 等待网络空闲
    load_dom: bool = True                # 等待 DOM 加载完成
    wait_selector: str | None = None     # 等待指定选择器出现
    wait_selector_state: str = "attached"  # 等待状态
    wait: int = 0                        # 额外等待毫秒数
    page_action: Callable | None = None  # 页面加载后自动化操作
    page_setup: Callable | None = None   # 页面导航前设置操作
    capture_xhr: str | None = None       # XHR 拦截 URL 正则

    # === 自适应爬取配置 ===
    adaptive: bool = False               # 启用自适应选择器
    adaptive_storage: str | None = None  # 自适应数据库路径

    # === 运行时注入属性（由 Runner 设置） ===
    _session: object | None = None       # Scrapling session 实例
    _stop_event: asyncio.Event | None = None

    def __init_subclass__(cls, **kwargs):
        """子类定义时校验"""
        super().__init_subclass__(**kwargs)
        if cls.__name__.startswith("_"):
            return
        if not cls.name:
            cls.name = cls.__name__

    async def run(self) -> AsyncGenerator[dict, None]:
        """核心爬取逻辑，yield 爬取的数据项。

        在 run() 内部通过 self 发起请求：
          - await self.get(url, **kwargs)      → HTTP GET，返回 Response
          - await self.post(url, data=, **kwargs) → HTTP POST，返回 Response
          - self.session                       → 当前 Scrapling session 实例
          - self.should_stop                   → bool，检查是否收到停止信号

        示例：
            async def run(self):
                page = await self.get("https://example.com")
                for item in page.css(".article"):
                    if self.should_stop:
                        break
                    yield {"title": item.css("h2::text").get("")}
        """
        raise NotImplementedError(f"{self.__class__.__name__} 必须实现 run() 方法")

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

    @property
    def session(self):
        """当前 Scrapling session 实例"""
        return self._session

    @property
    def should_stop(self) -> bool:
        """检查是否收到停止信号"""
        if self._stop_event is None:
            return False
        return self._stop_event.is_set()

    async def get(self, url: str, **kwargs) -> Response:
        """HTTP GET 请求

        自动应用爬虫配置的默认参数（headers、cookies、encoding 等），
        调用时传入的 kwargs 优先级更高。
        """
        if self._session is None:
            raise RuntimeError("session 未初始化，爬虫必须通过 Runner 启动")
        merged = self._merge_request_kwargs(kwargs)
        return await self._session.get(url, **merged)

    async def post(self, url: str, **kwargs) -> Response:
        """HTTP POST 请求

        自动应用爬虫配置的默认参数。
        """
        if self._session is None:
            raise RuntimeError("session 未初始化，爬虫必须通过 Runner 启动")
        merged = self._merge_request_kwargs(kwargs)
        return await self._session.post(url, **merged)

    def _merge_request_kwargs(self, kwargs: dict) -> dict:
        """合并爬虫默认配置与请求级参数，请求级优先"""
        merged = {}
        if self.default_headers:
            merged["headers"] = {**self.default_headers, **kwargs.get("headers", {})}
        if self.cookies:
            merged["cookies"] = {**self.cookies, **kwargs.get("cookies", {})}
        if self.encoding and "selector_config" not in kwargs:
            merged["selector_config"] = {"adaptive": self.adaptive}
        if self.follow_redirects is False:
            merged.setdefault("follow_redirects", False)
        if self.proxies and "proxy" not in kwargs and "proxy_rotator" not in kwargs:
            merged["proxy"] = self.proxies[0]
        # 请求级参数覆盖默认
        merged.update(kwargs)
        return merged
