"""模板爬虫 — RuleSpider、SitemapRuleSpider"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from openspider.spiders.base import BaseSpider


class RuleSpider(BaseSpider):
    """规则驱动爬虫

    通过 rules() 声明链接跟进规则，类似 Scrapy 的 CrawlSpider。
    每条规则包含一个 LinkExtractor 和一个可选的回调方法。

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
        """返回 CrawlRule 列表

        每条规则包含：
        - link_extractor: LinkExtractor 实例
        - callback: 回调方法（可选）
        - priority: 请求优先级（可选）
        """
        raise NotImplementedError(f"{self.__class__.__name__} 必须实现 rules() 方法")

    async def run(self) -> AsyncGenerator[dict, None]:
        """使用 Scrapling CrawlSpider 引擎执行规则"""
        from scrapling.spiders import CrawlSpider, CrawlRule, LinkExtractor

        # 动态创建 Scrapling CrawlSpider 子类
        spider_cls = self._create_scrapling_spider()
        spider = spider_cls(crawldir=str(self._get_crawldir()))

        result = spider.start()
        for item in result.items:
            yield item

    def _create_scrapling_spider(self):
        """动态创建 Scrapling CrawlSpider 子类"""
        from scrapling.spiders import CrawlSpider, CrawlRule, LinkExtractor, Response

        rules_list = self.rules()
        base_self = self

        class DynamicCrawlSpider(CrawlSpider):
            name = base_self.name
            start_urls = base_self.start_urls
            concurrent_requests = base_self.concurrent_requests
            download_delay = base_self.download_delay
            robots_txt_obey = False

            def rules(self_inner):
                return rules_list

        # 为每条规则绑定回调
        for rule in rules_list:
            if rule.callback and callable(rule.callback):
                # 将 BaseSpider 的回调绑定到 DynamicCrawlSpider
                callback_name = rule.callback.__name__
                setattr(DynamicCrawlSpider, callback_name, rule.callback)
                rule.callback = getattr(DynamicCrawlSpider, callback_name)

        return DynamicCrawlSpider

    def _get_crawldir(self):
        """获取断点目录"""
        from openspider.config import settings
        return settings.crawl_data_dir / self.name


class SitemapRuleSpider(BaseSpider):
    """Sitemap 驱动爬虫

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

    sitemap_urls: list[str] = []         # sitemap URL 列表
    sitemap_follow: object | None = None  # 过滤要跟进的子 sitemap
    sitemap_alternate_links: bool = False  # 是否提取多语言 alternate 链接

    def rules(self) -> list:
        """返回 CrawlRule 列表"""
        raise NotImplementedError(f"{self.__class__.__name__} 必须实现 rules() 方法")

    async def run(self) -> AsyncGenerator[dict, None]:
        """使用 Scrapling SitemapSpider 引擎执行"""
        from scrapling.spiders import SitemapSpider, CrawlRule, LinkExtractor

        spider_cls = self._create_scrapling_spider()
        spider = spider_cls(crawldir=str(self._get_crawldir()))

        result = spider.start()
        for item in result.items:
            yield item

    def _create_scrapling_spider(self):
        """动态创建 Scrapling SitemapSpider 子类"""
        from scrapling.spiders import SitemapSpider, CrawlRule, LinkExtractor, Response

        rules_list = self.rules()
        base_self = self

        class DynamicSitemapSpider(SitemapSpider):
            name = base_self.name
            sitemap_urls = base_self.sitemap_urls
            sitemap_alternate_links = base_self.sitemap_alternate_links
            concurrent_requests = base_self.concurrent_requests
            download_delay = base_self.download_delay

            def rules(self_inner):
                return rules_list

        if self.sitemap_follow:
            DynamicSitemapSpider.sitemap_follow = self.sitemap_follow

        for rule in rules_list:
            if rule.callback and callable(rule.callback):
                callback_name = rule.callback.__name__
                setattr(DynamicSitemapSpider, callback_name, rule.callback)
                rule.callback = getattr(DynamicSitemapSpider, callback_name)

        return DynamicSitemapSpider

    def _get_crawldir(self):
        """获取断点目录"""
        from openspider.config import settings
        return settings.crawl_data_dir / self.name
