"""示例爬虫 — 爬取名言网站"""

from openspider.spiders.base import BaseSpider


class QuotesSpider(BaseSpider):
    """爬取 quotes.toscrape.com 的名言数据"""

    name = "quotes"
    description = "示例爬虫：爬取名言网站"
    start_urls = ["https://quotes.toscrape.com/"]
    concurrent_requests = 2
    download_delay = 0.5

    async def run(self):
        url = self.start_urls[0]
        while url:
            if self.should_stop:
                break

            page = await self.get(url)

            for quote in page.css("div.quote"):
                yield {
                    "text": quote.css("span.text::text").get(""),
                    "author": quote.css("small.author::text").get(""),
                    "tags": quote.css("a.tag::text").getall(),
                }

            # 翻页
            next_btn = page.css("li.next a")
            if next_btn:
                url = self.start_urls[0].rstrip("/") + next_btn.attrib.get("href", "")
            else:
                break
