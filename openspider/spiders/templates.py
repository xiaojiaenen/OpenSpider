"""模板爬虫 — RuleSpider、SitemapRuleSpider

包装 Scrapling 的 CrawlSpider / SitemapSpider，
正确转发用户配置，支持暂停恢复（crawldir）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from openspider.spiders.base import BaseSpider


class RuleSpider(BaseSpider):
    """规则驱动爬虫（包装 Scrapling CrawlSpider）

    通过 rules() 声明链接跟进规则。

    示例：
        class BlogCrawler(RuleSpider):
            name = "blog"
            start_urls = ["https://example.com"]

            def rules(self):
                return [
                    CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
                    CrawlRule(LinkExtractor(allow=r"/page/\\d+/")),
                ]

            async def parse_post(self, response):
                yield {"title": response.css("h1::text").get("")}
    """

    def rules(self) -> list:
        """返回 CrawlRule 列表"""
        raise NotImplementedError(f"{self.__class__.__name__} 必须实现 rules() 方法")

    async def run(self) -> AsyncGenerator[dict, None]:
        """使用 Scrapling CrawlSpider 引擎执行规则"""
        scrapling_spider_cls = self._create_scrapling_spider()
        scrapling_spider = scrapling_spider_cls(crawldir=str(self._get_crawldir()))

        # Scrapling Spider.start() 是同步阻塞的，放到线程池
        result = await asyncio.to_thread(scrapling_spider.start)

        if hasattr(result, 'items'):
            for item in result.items:
                if self.should_stop:
                    break
                yield item

    def _create_scrapling_spider(self):
        """动态创建 Scrapling CrawlSpider 子类，正确转发配置"""
        from scrapling.spiders import CrawlSpider, CrawlRule, LinkExtractor, Response

        rules_list = self.rules()
        base_self = self

        class DynamicCrawlSpider(CrawlSpider):
            name = base_self.name
            start_urls = base_self.start_urls
            concurrent_requests = base_self.concurrent_requests
            download_delay = base_self.download_delay
            robots_txt_obey = base_self.robots_txt_obey
            development_mode = base_self.development_mode

            def rules(self_inner):
                return rules_list

            async def parse(self_inner, response: Response):
                """桥接：调用用户的 parse()（如果有）或默认行为"""
                # CrawlSpider 的默认 parse 会根据 rules 分发
                # 如果用户重写了 parse，需要手动调用
                user_parse = getattr(base_self, '_user_parse', None)
                if user_parse:
                    async for result in user_parse(response):
                        yield result

        # 绑定用户回调
        for rule in rules_list:
            if rule.callback and callable(rule.callback):
                callback_name = rule.callback.__name__
                # 保存用户的 parse 方法引用
                if callback_name == 'parse':
                    base_self._user_parse = rule.callback
                else:
                    # 将用户回调绑定到 DynamicSpider
                    async def make_wrapper(cb):
                        async def wrapper(self_inner, response):
                            # 调用用户的回调（base_self 上的方法）
                            async for result in cb(response):
                                yield result
                        return wrapper
                    # 注意：这里需要异步包装
                    setattr(DynamicCrawlSpider, callback_name, rule.callback)

        return DynamicCrawlSpider

    def _get_crawldir(self):
        from openspider.config import settings
        return settings.crawl_data_dir / self.name


class SitemapRuleSpider(BaseSpider):
    """Sitemap 驱动爬虫（包装 Scrapling SitemapSpider）

    从 sitemap.xml 提取 URL 并按规则分发。

    示例：
        class ProductSitemap(SitemapRuleSpider):
            name = "products"
            sitemap_urls = ["https://shop.example.com/sitemap.xml"]

            def rules(self):
                return [
                    CrawlRule(LinkExtractor(allow=r"/products/"), callback=self.parse_product),
                ]

            async def parse_product(self, response):
                yield {"name": response.css("h1::text").get("")}
    """

    sitemap_urls: list[str] = []
    sitemap_follow: object | None = None
    sitemap_alternate_links: bool = False

    def rules(self) -> list:
        raise NotImplementedError(f"{self.__class__.__name__} 必须实现 rules() 方法")

    async def run(self) -> AsyncGenerator[dict, None]:
        scrapling_spider_cls = self._create_scrapling_spider()
        scrapling_spider = scrapling_spider_cls(crawldir=str(self._get_crawldir()))

        result = await asyncio.to_thread(scrapling_spider.start)

        if hasattr(result, 'items'):
            for item in result.items:
                if self.should_stop:
                    break
                yield item

    def _create_scrapling_spider(self):
        from scrapling.spiders import SitemapSpider, CrawlRule, LinkExtractor, Response

        rules_list = self.rules()
        base_self = self

        class DynamicSitemapSpider(SitemapSpider):
            name = base_self.name
            sitemap_urls = base_self.sitemap_urls
            sitemap_alternate_links = base_self.sitemap_alternate_links
            concurrent_requests = base_self.concurrent_requests
            download_delay = base_self.download_delay
            robots_txt_obey = base_self.robots_txt_obey
            development_mode = base_self.development_mode

            def rules(self_inner):
                return rules_list

        if self.sitemap_follow:
            DynamicSitemapSpider.sitemap_follow = self.sitemap_follow

        # 绑定用户回调
        for rule in rules_list:
            if rule.callback and callable(rule.callback):
                callback_name = rule.callback.__name__
                setattr(DynamicSitemapSpider, callback_name, rule.callback)

        return DynamicSitemapSpider

    def _get_crawldir(self):
        from openspider.config import settings
        return settings.crawl_data_dir / self.name
