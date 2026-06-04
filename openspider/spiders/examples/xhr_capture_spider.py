"""XHR/API 拦截示例爬虫

演示 Scrapling 的 capture_xhr 能力：
拦截页面加载时的 XHR/Fetch API 调用，直接获取结构化数据。
适用于 SPA（单页应用）网站，数据通过 JavaScript 异步加载。
"""

from openspider.spiders.base import BaseSpider


class XHRCaptureSpider(BaseSpider):
    """XHR/API 拦截示例

    演示如何用 capture_xhr 拦截 SPA 应用的 API 请求。
    适用于 React/Vue/Angular 等前端框架构建的网站，
    页面数据通过 XHR/Fetch API 异步加载。

    使用方式：
        1. 设置 capture_xhr 为要拦截的 API URL 正则
        2. 使用 use_stealth=True + wait_selector 确保页面加载完成
        3. 从 page.captured_xhr 获取拦截到的 Response 列表
    """
    name = "xhr_capture_demo"
    description = "XHR/API 拦截示例 — 演示 capture_xhr 捕获 SPA 数据"
    start_urls = ["https://quotes.toscrape.com/js/"]
    use_stealth = True  # SPA 页面通常需要浏览器渲染
    network_idle = True  # 等待所有 XHR 完成

    # 要拦截的 API URL 正则模式
    capture_xhr = r"https://quotes\.toscrape\.com/.*"

    # 等待页面关键元素出现（确保 JS 渲染完成）
    wait_selector = ".quote"

    async def run(self):
        """简单模式：通过浏览器加载页面，获取渲染后的内容"""
        page = await self.get(self.start_urls[0])
        if not page:
            return

        # 获取渲染后的页面内容
        for quote in page.css(".quote"):
            if self.should_stop:
                break
            yield {
                "type": "rendered",
                "text": quote.css(".text::text").get(""),
                "author": quote.css(".author::text").get(""),
                "tags": quote.css(".tag::text").getall(),
            }

        # 如果有拦截到的 XHR 数据，也可以处理
        if hasattr(page, 'captured_xhr') and page.captured_xhr:
            for xhr in page.captured_xhr:
                if self.should_stop:
                    break
                try:
                    data = xhr.json() if hasattr(xhr, 'json') else None
                    if data:
                        yield {
                            "type": "xhr_data",
                            "url": str(xhr.url) if hasattr(xhr, 'url') else "",
                            "status": xhr.status if hasattr(xhr, 'status') else 0,
                            "data": data,
                        }
                except Exception:
                    pass


class SPAApiSpider(BaseSpider):
    """SPA API 数据抓取示例

    更实用的示例：拦截 SPA 应用的 API 接口，直接获取 JSON 数据，
    避免解析复杂的 DOM 结构。

    子类只需覆盖 api_pattern 和 parse_api_data。
    """
    name = "spa_api_demo"
    description = "SPA API 拦截 — 直接获取 API 返回的 JSON 数据"
    start_urls: list[str] = []  # 子类需要设置
    use_stealth = True
    network_idle = True

    # API URL 正则 — 子类覆盖
    api_pattern: str = r"https://api\.example\.com/.*"

    # 页面加载等待选择器 — 子类覆盖
    wait_selector: str | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 自动设置 capture_xhr
        if cls.api_pattern:
            cls.capture_xhr = cls.api_pattern

    async def parse_api_data(self, data: dict, url: str) -> dict | None:
        """解析 API 返回数据 — 子类覆盖此方法

        Args:
            data: API 返回的 JSON 数据
            url: API 请求 URL

        Returns:
            处理后的数据字典，或 None 丢弃
        """
        return data

    async def run(self):
        """入口：拦截 API 并处理数据"""
        for url in self.start_urls:
            if self.should_stop:
                break

            page = await self.get(url)
            if not page:
                continue

            # 处理拦截到的 XHR 数据
            if hasattr(page, 'captured_xhr'):
                for xhr in page.captured_xhr:
                    if self.should_stop:
                        break
                    try:
                        data = xhr.json() if hasattr(xhr, 'json') else None
                        if data:
                            result = await self.parse_api_data(
                                data,
                                str(xhr.url) if hasattr(xhr, 'url') else url,
                            )
                            if result:
                                yield result
                    except Exception as e:
                        await self.on_error(e)
