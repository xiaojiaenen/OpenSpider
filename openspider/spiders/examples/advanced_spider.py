"""示例爬虫 — 高级模式（parse 回调 + 多级跟进 + 并发）"""

from openspider.spiders.base import BaseSpider


class AdvancedQuotesSpider(BaseSpider):
    """使用 parse() 回调模式爬取 quotes.toscrape.com

    演示：
    - parse() 回调提取列表页链接
    - parse_detail() 回调提取详情页数据
    - 自动跟进分页
    """

    name = "advanced_quotes"
    description = "高级模式示例：回调式爬取名言网站"
    start_urls = ["https://quotes.toscrape.com/"]
    concurrent_requests = 4
    download_delay = 0.3

    async def parse(self, response):
        """列表页：提取名言 + 跟进分页"""
        # 提取当前页名言
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(""),
                "author": quote.css("small.author::text").get(""),
                "tags": quote.css("a.tag::text").getall(),
            }

        # 跟进下一页
        next_btn = response.css("li.next a")
        if next_btn:
            href = next_btn[0].attrib.get("href", "")
            yield self.follow(
                self.start_urls[0].rstrip("/") + href,
                callback=self.parse,
            )
