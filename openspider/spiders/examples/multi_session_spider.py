"""多 Session 路由示例爬虫

演示 Scrapling 的 configure_sessions 能力：
- 普通页面走 FetcherSession（快速 TLS 指纹）
- 反爬保护页面走 AsyncStealthySession（隐身浏览器）

通过 yield Request(sid="stealth") 路由请求到不同 session。
"""

from openspider.spiders.base import BaseSpider
from scrapling.spiders import CrawlRule, LinkExtractor


class MultiSessionSpider(BaseSpider):
    """多 Session 路由示例

    演示如何在同一爬虫内混合使用快速 HTTP 请求和隐身浏览器。
    普通页面走默认 session，需要反爬绕过的页面走 stealth session。

    使用方式：
        1. 继承本类或参考本类实现自己的爬虫
        2. 在 parse() 中根据 URL 特征选择 session（sid）
        3. 平台会自动通过 configure_sessions 配置多个 session
    """
    name = "multi_session_demo"
    description = "多 Session 路由示例 — 演示 Fetcher + Stealthy 混合模式"
    start_urls = ["https://quotes.toscrape.com/"]
    use_stealth = False  # 基础模式不使用 stealth，通过 sid 按需路由

    # 需要走隐身浏览器的 URL 模式列表（子类可覆盖）
    stealth_url_patterns: list[str] = ["/protected", "/login", "/verify"]

    async def run(self):
        """简单模式入口：通过 Scrapling Spider 框架运行

        注意：多 Session 路由需要使用 parse() 高级模式
        本示例的 parse() 已实现路由逻辑。
        """
        # 简单模式：直接抓取
        page = await self.get(self.start_urls[0])
        for quote in page.css(".quote"):
            if self.should_stop:
                break
            yield {
                "text": quote.css(".text::text").get(""),
                "author": quote.css(".author::text").get(""),
            }

    async def parse(self, response):
        """高级模式：通过 sid 路由到不同 session

        需要反爬绕过的 URL 用 sid="stealth"，其余用默认 session。
        """
        # 提取当前页面的所有链接
        for link in response.css("a::attr(href)").getall():
            if self.should_stop:
                break
            full_url = response.urljoin(link) if hasattr(response, 'urljoin') else link

            # 根据 URL 特征选择 session
            needs_stealth = any(pat in full_url for pat in self.stealth_url_patterns)
            if needs_stealth:
                from scrapling.spiders import Request
                yield Request(full_url, sid="stealth", callback=self.parse_stealth_page)
            else:
                yield response.follow(full_url, callback=self.parse_normal_page)

    async def parse_normal_page(self, response):
        """普通页面解析"""
        yield {
            "type": "normal",
            "url": response.url,
            "title": response.css("title::text").get(""),
        }

    async def parse_stealth_page(self, response):
        """隐身页面解析（通过 StealthySession 抓取）"""
        yield {
            "type": "stealth",
            "url": response.url,
            "title": response.css("title::text").get(""),
        }

    def configure_sessions(self, manager):
        """配置多 session：快速 HTTP + 隐身浏览器

        此方法会被平台的 Runner 自动调用，
        注册 "default"（Fetcher）和 "stealth"（Stealthy）两个 session。
        """
        from scrapling.fetchers import FetcherSession, AsyncStealthySession

        # 默认 session：快速 HTTP 请求
        manager.add("default", FetcherSession(
            impersonate=self.impersonate,
            verify=self.ssl_verify,
            timeout=self.timeout,
        ))

        # 隐身 session：浏览器自动化 + 反爬绕过
        manager.add("stealth", AsyncStealthySession(
            headless=True,
            solve_cloudflare=self.solve_cloudflare,
            block_webrtc=self.block_webrtc,
            hide_canvas=self.hide_canvas,
            block_ads=self.block_ads,
        ), lazy=True)  # lazy=True：只在首次使用时启动浏览器
