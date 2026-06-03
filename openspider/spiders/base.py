"""爬虫基类 — 包装 Scrapling Spider，复用其全部能力"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapling.operators import Response


class BaseSpider:
    """爬虫基类

    支持两种模式：
    1. 简单模式 — 实现 run()，用 self.get()/self.post() 请求，yield 数据项
    2. 高级模式 — 实现 parse(response)，用 Request/Response 回调模式

    平台会自动将配置转发给 Scrapling Spider，复用其并发、去重、代理轮换、暂停恢复等能力。
    """

    # === 基本信息 ===
    name: str = ""
    description: str = ""
    start_urls: list[str] = []
    schedule: str | None = None
    max_retries: int = 3
    retry_delay: int = 60
    concurrent_requests: int = 4
    download_delay: float = 0.5
    robots_txt_obey: bool = False
    use_stealth: bool = False
    proxies: list[str] = []

    # === 网站兼容性 ===
    # encoding 由 Scrapling 自动检测处理，不需要手动指定
    ssl_verify: bool = True
    follow_redirects: bool = True
    timeout: int = 30
    default_headers: dict = {}
    cookies: dict = {}

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

    # === 开发模式 ===
    development_mode: bool = False  # 缓存响应到磁盘，开发调试用

    # === 运行时参数 ===
    params: dict = {}
    _env_overrides: dict = {}

    # === 运行时注入（由 Runner 设置） ===
    _session: object | None = None
    _stop_event: asyncio.Event | None = None
    _scrapling_response: object | None = None  # 当前回调模式下的 response

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__.startswith("_"):
            return
        if not cls.name:
            cls.name = cls.__name__

    # ============================================================
    #  简单模式：run() 异步生成器
    # ============================================================

    async def run(self):
        """简单模式入口。用 self.get()/self.post() 请求，yield 数据项。

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

    async def parse(self, response):
        """高级模式入口。用 Request/Response 回调模式。

        支持 yield dict（数据项）、Request（跟进请求）、None（忽略）。
        自动使用 Scrapling 的并发、去重、代理轮换。

        示例：
            async def parse(self, response):
                for link in response.css("a::attr(href)").getall():
                    yield self.follow(link, callback=self.parse_detail)
                yield {"url": response.url}

            async def parse_detail(self, response):
                yield {"title": response.css("h1::text").get("")}
        """
        async for item in self.run():
            yield item

    def request(self, url: str, callback=None, **kwargs):
        """创建 Request 对象（高级模式用）"""
        from scrapling.spiders import Request
        return Request(url, callback=callback or self.parse, **kwargs)

    def follow(self, url: str, response=None, callback=None, **kwargs):
        """从当前页面跟进链接（高级模式用）

        如果传入 response，自动使用 response.follow() 解析相对 URL 和设置 Referer。
        """
        if response is not None:
            return response.follow(url, callback=callback or self.parse, **kwargs)
        from scrapling.spiders import Request
        return Request(url, callback=callback or self.parse, **kwargs)

    # ============================================================
    #  直接请求方法
    # ============================================================

    async def fetch(self, url: str, **kwargs) -> Response:
        """直接抓取页面"""
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
                               callback=None):
        """并发抓取多个 URL"""
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
        pass

    async def on_error(self, error: Exception):
        pass

    async def on_complete(self):
        pass

    async def on_item_scraped(self, item: dict) -> dict | None:
        return item

    # ============================================================
    #  属性和工具
    # ============================================================

    @property
    def session(self):
        return self._session

    @property
    def should_stop(self) -> bool:
        if self._stop_event is None:
            return False
        return self._stop_event.is_set()

    def env(self, key: str, default: str | None = None) -> str | None:
        if key in self._env_overrides:
            return self._env_overrides[key]
        return os.environ.get(key, default)

    def _merge_request_kwargs(self, kwargs: dict) -> dict:
        merged = {}
        if self.default_headers:
            merged["headers"] = {**self.default_headers, **kwargs.get("headers", {})}
        if self.cookies:
            merged["cookies"] = {**self.cookies, **kwargs.get("cookies", {})}
        if self.follow_redirects is False:
            merged.setdefault("follow_redirects", False)
        merged.update(kwargs)
        return merged
