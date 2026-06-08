"""AI 生成的测试爬虫 — 爬取 books.toscrape.com"""
from openspider.spiders.base import BaseSpider


class BooksSpider(BaseSpider):
    name = "books_test"
    description = "AI 生成的测试爬虫：爬取书籍网站"
    start_urls = ["https://books.toscrape.com/"]
    concurrent_requests = 2
    download_delay = 0.3

    fields = [
        {"name": "title", "type": "VARCHAR(512)"},
        {"name": "price", "type": "VARCHAR(64)"},
        {"name": "availability", "type": "VARCHAR(128)"},
        {"name": "rating", "type": "VARCHAR(64)"},
    ]

    async def run(self):
        page = await self.get(self.start_urls[0])
        for book in page.css("article.product_pod"):
            yield {
                "title": book.css("h3 a::attr(title)").get(""),
                "price": book.css("p.price_color::text").get(""),
                "availability": book.css("p.instock.availability::text").get("").strip(),
                "rating": book.css("p.star-rating::attr(class)").get("").replace("star-rating ", ""),
            }
