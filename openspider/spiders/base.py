"""爬虫基类 — 包装 Scrapling Spider，支持简单/高级/专家三种模式"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapling.operators import Response


class BaseSpider:
    """爬虫基类

    支持三种编写模式：

    1. 简单模式 — 实现 run()，用 self.get()/self.post() 请求，yield 数据项：
        async def run(self):
            page = await self.get("https://example.com")
            for item in page.css(".article"):
                yield {"title": item.css("h2::text").get("")}

    2. 高级模式 — 实现 parse(response)，用 Request/Response 回调模式：
        async def parse(self, response):
            for link in response.css("a::attr(href)").getall():
                yield self.follow(link, callback=self.parse_detail)
            yield {"url": response.url}

        async def parse_detail(self, response):
            yield {"title": response.css("h1::text").get("")}

    3. 专家模式 — 直接使用 Scrapling 的 Spider 能力：
        配置 configure_sessions() 使用多 session、代理轮换等。
    """

    # === 基本信息 ===
    name: str = ""                       # 唯一标识
    description: str = ""                # 爬虫描述
    start_urls: list[str] = []           # 入口 URL 列表
    schedule: str | None = None          # cron 表达式
    max_retries: int = 3                 # 失败重试次数
    retry_delay: int = 60                # 重试间隔（秒）
    concurrent_requests: int = 4         # 并发请求数
    download_delay: float = 0.5          # 请求间隔（秒）
    robots_txt_obey: bool = False        # 遵守 robots.txt
    use_stealth: bool = False            # 隐身模式
    proxies: list[str] = []              # 代理列表

    # === 网站兼容性 ===
    encoding: str | None = None          # 强制编码
    ssl_verify: bool = True              # SSL 证书验证
    follow_redirects: bool = True        # 跟随重定向
    timeout: int = 30                    # 超时秒数
    default_headers: dict = {}           # 默认请求头
    cookies: dict = {}                   # 预设 Cookie

    # === 反爬与指纹 ===
    impersonate: str | list[str] = "chrome"
    http3: bool = False
    stealthy_headers: bool = True
    block_ads: bool = False
    blocked_domains: set[str] = set()
    dns_over_https: bool = False
    locale: str | None = None
    timezone_id: str | None = None

    # === 浏览器高级配置 ===
    solve_cloudflare: bool = False
    block_webrtc: bool = False
    hide_canvas: bool = False
    allow_webgl: bool = True
    real_chrome: bool = False
    cdp_url: str | None = None
    user_data_dir: str | None = None
    init_script: str | None = None
    max_pages: int = 1
    disable_resources: bool = True
    network_idle: bool = False
    load_dom: bool = True
    wait_selector: str | None = None
    wait_selector_state: str = "attached"
    wait: int = 0
    page_action: Callable | None = None
    page_setup: Callable | None = None
    capture_xhr: str | None = None

    # === 自适应 ===
    adaptive: bool = False
    adaptive_storage: str | None = None

    # === 运行时参数 ===
    params: dict = {}
    _env_overrides: dict = {}

    # === 运行时注入（由 Runner 设置） ===
    _session: object | None = None
    _stop_event: asyncio.Event | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__.startswith("_"):
            return
        if not cls.name:
            cls.name = cls.__name__

    # ============================================================
    #  简单模式：run() 异步生成器
    # ============================================================

    async def run(self) -> AsyncGenerator[dict, None]:
        """简单模式入口。子类实现此方法，用 self.get()/self.post() 请求，yield 数据项。

        示例：
            async def run(self):
                page = await self.get("https://example.com")
                for item in page.css(".article"):
                    if self.should_stop:
                        break
                    yield {"title": item.css("h2::text").get("")}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 必须实现 run() 或 parse() 方法"
        )

    # ============================================================
    #  高级模式：parse(response) 回调模式
    # ============================================================

    async def parse(self, response) -> AsyncGenerator:
        """高级模式入口。子类实现此方法，用 Request/Response 回调模式。

        支持 yield dict（数据项）、Request（跟进请求）、None（忽略）。

        示例：
            async def parse(self, response):
                for link in response.css("a::attr(href)").getall():
                    yield self.follow(link, callback=self.parse_detail)
                yield {"url": response.url}

            async def parse_detail(self, response):
                yield {"title": response.css("h1::text").get("")}
        """
        # 默认 fallback 到 run() 模式
        async for item in self.run():
            yield item

    def request(self, url: str, callback=None, **kwargs):
        """创建 Request 对象（高级模式用）

        Args:
            url: 目标 URL
            callback: 回调方法（默认 self.parse）
            **kwargs: 传递给 Scrapling Request 的参数

        Returns:
            Scrapling Request 对象
        """
        from scrapling.spiders import Request
        return Request(
            url,
            callback=callback or self.parse,
            **kwargs,
        )

    def follow(self, url: str, response=None, callback=None, **kwargs):
        """从当前页面跟进链接（高级模式用）

        自动处理相对 URL、设置 Referer 头。

        Args:
            url: 目标 URL（相对或绝对）
            response: 当前页面 Response（用于解析相对 URL）
            callback: 回调方法
            **kwargs: 额外参数

        Returns:
            Scrapling Request 对象
        """
        from scrapling.spiders import Request
        return Request(
            url,
            callback=callback or self.parse,
            **kwargs,
        )

    # ============================================================
    #  直接请求方法（简单模式用）
    # ============================================================

    async def fetch(self, url: str, **kwargs) -> Response:
        """直接抓取页面，返回 Response 对象

        简单模式下推荐用 self.get()/self.post()，
        此方法提供更多控制，等同于 Scrapling 的 Fetcher。
        """
        return await self.get(url, **kwargs)

    async def get(self, url: str, **kwargs) -> Response:
        """HTTP GET 请求"""
        if self._session is None:
            raise RuntimeError("session 未初始化，爬虫必须通过 Runner 启动")
        merged = self._merge_request_kwargs(kwargs)
        return await self._session.get(url, **merged)

    async def post(self, url: str, **kwargs) -> Response:
        """HTTP POST 请求"""
        if self._session is None:
            raise RuntimeError("session 未初始化，爬虫必须通过 Runner 启动")
        merged = self._merge_request_kwargs(kwargs)
        return await self._session.post(url, **merged)

    # ============================================================
    #  并发请求
    # ============================================================

    async def concurrent_fetch(self, urls: list[str], max_concurrent: int = 10,
                               callback=None) -> AsyncGenerator:
        """并发抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrent: 最大并发数
            callback: 每个响应的回调（可选）

        Yields:
            每个 URL 的 Response 对象或回调结果
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _fetch_one(url):
            async with semaphore:
                if self.should_stop:
                    return None
                try:
                    resp = await self.get(url)
                    if callback:
                        return callback(resp)
                    return resp
                except Exception as e:
                    await self.on_error(e)
                    return None

        tasks = [_fetch_one(url) for url in urls]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                yield result

    # ============================================================
    #  生命周期钩子
    # ============================================================

    async def on_start(self, resuming: bool = False):
        """启动前钩子"""
        pass

    async def on_error(self, error: Exception):
        """出错时钩子"""
        pass

    async def on_complete(self):
        """完成时钩子"""
        pass

    async def on_item_scraped(self, item: dict) -> dict | None:
        """每条数据后处理，返回 None 丢弃"""
        return item

    # ============================================================
    #  属性和工具方法
    # ============================================================

    @property
    def session(self):
        """当前 Scrapling session"""
        return self._session

    @property
    def should_stop(self) -> bool:
        """检查停止信号"""
        if self._stop_event is None:
            return False
        return self._stop_event.is_set()

    def env(self, key: str, default: str | None = None) -> str | None:
        """读取环境变量（敏感参数用）"""
        if key in self._env_overrides:
            return self._env_overrides[key]
        return os.environ.get(key, default)

    def _merge_request_kwargs(self, kwargs: dict) -> dict:
        """合并默认配置与请求级参数"""
        merged = {}
        if self.default_headers:
            merged["headers"] = {**self.default_headers, **kwargs.get("headers", {})}
        if self.cookies:
            merged["cookies"] = {**self.cookies, **kwargs.get("cookies", {})}
        if self.follow_redirects is False:
            merged.setdefault("follow_redirects", False)
        if self.proxies and "proxy" not in kwargs and "proxy_rotator" not in kwargs:
            merged["proxy"] = self.proxies[0]
        merged.update(kwargs)
        return merged
