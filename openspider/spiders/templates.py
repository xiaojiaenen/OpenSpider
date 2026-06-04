"""模板爬虫 — RuleSpider、SitemapRuleSpider

包装 Scrapling 的 CrawlSpider / SitemapSpider，
通过 scrapling_utils 统一转发全部配置。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from openspider.spiders.base import BaseSpider
from openspider.core.scrapling_utils import (
    build_session_kwargs, build_stealth_kwargs, inject_proxy, configure_session,
)


class RuleSpider(BaseSpider):
    """规则驱动爬虫（包装 Scrapling CrawlSpider）

    示例：
        class BlogCrawler(RuleSpider):
            name = "blog"
            start_urls = ["https://example.com"]

            def rules(self):
                return [
                    CrawlRule(LinkExtractor(allow=r"/posts/"), callback=self.parse_post),
                ]

            async def parse_post(self, response):
                yield {"title": response.css("h1::text").get("")}
    """

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
        from scrapling.spiders import CrawlSpider, Response

        base_self = self
        rules_list = self.rules()

        class DynamicCrawlSpider(CrawlSpider):
            name = base_self.name
            start_urls = base_self.start_urls
            concurrent_requests = base_self.concurrent_requests
            download_delay = base_self.download_delay
            robots_txt_obey = base_self.robots_txt_obey
            development_mode = base_self.development_mode

            def configure_sessions(self_inner, manager):
                configure_session(manager, base_self)

            def rules(self_inner):
                return rules_list

        # 正确绑定回调：保留原始 bound method 的引用
        for rule in rules_list:
            if rule.callback and callable(rule.callback):
                cb = rule.callback  # 保留 bound method 引用
                cb_name = cb.__name__
                # 创建闭包包装，避免 setattr 问题
                def make_wrapper(callback):
                    async def wrapper(self_inner, response: Response):
                        async for result in callback(response):
                            yield result
                    wrapper.__name__ = callback.__name__
                    return wrapper
                setattr(DynamicCrawlSpider, cb_name, make_wrapper(cb))

        return DynamicCrawlSpider

    def _get_crawldir(self):
        from openspider.config import settings
        return settings.crawl_data_dir / self.name


class SitemapRuleSpider(BaseSpider):
    """Sitemap 驱动爬虫（包装 Scrapling SitemapSpider）

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
        from scrapling.spiders import SitemapSpider, Response

        base_self = self
        rules_list = self.rules()

        class DynamicSitemapSpider(SitemapSpider):
            name = base_self.name
            sitemap_urls = base_self.sitemap_urls
            sitemap_alternate_links = base_self.sitemap_alternate_links
            concurrent_requests = base_self.concurrent_requests
            download_delay = base_self.download_delay
            robots_txt_obey = base_self.robots_txt_obey
            development_mode = base_self.development_mode

            def configure_sessions(self_inner, manager):
                configure_session(manager, base_self)

            def rules(self_inner):
                return rules_list

        if self.sitemap_follow:
            DynamicSitemapSpider.sitemap_follow = self.sitemap_follow

        for rule in rules_list:
            if rule.callback and callable(rule.callback):
                cb = rule.callback
                def make_wrapper(callback):
                    async def wrapper(self_inner, response: Response):
                        async for result in callback(response):
                            yield result
                    wrapper.__name__ = callback.__name__
                    return wrapper
                setattr(DynamicSitemapSpider, cb.__name__, make_wrapper(cb))

        return DynamicSitemapSpider

    def _get_crawldir(self):
        from openspider.config import settings
        return settings.crawl_data_dir / self.name
