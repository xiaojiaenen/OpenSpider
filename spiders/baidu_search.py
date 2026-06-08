from openspider.spiders.base import BaseSpider


class BaiduSearchSpider(BaseSpider):
    name = "baidu_search"
    description = "Baidu search spider"
    search_keywords = ["Python"]
    use_stealth = False
    impersonate = "chrome"
    download_delay = 2.0
    concurrent_requests = 2
    timeout = 30

    fields = [
        {"name": "keyword", "type": "VARCHAR(512)"},
        {"name": "rank", "type": "INTEGER"},
        {"name": "title", "type": "VARCHAR(512)"},
        {"name": "link", "type": "VARCHAR(2048)"},
        {"name": "abstract", "type": "TEXT"},
        {"name": "page_title", "type": "VARCHAR(512)"},
        {"name": "page_content", "type": "TEXT"},
    ]

    async def run(self):
        for keyword in self.search_keywords:
            if self.should_stop:
                break
            search_url = f"https://www.baidu.com/s?wd={keyword}&pn=0"
            page = await self.get(search_url)
            if not page:
                continue
            results = page.css("#content_left .result")
            for i, result in enumerate(results):
                if self.should_stop:
                    break
                title_elem = result.css("h3 a")
                title = title_elem.css("::text").get("").strip()
                link = title_elem.css("::attr(href)").get("")
                abstract = result.css(".c-abstract::text").getall()
                abstract_text = " ".join([a.strip() for a in abstract if a.strip()])
                if not title or not link:
                    continue
                page_content = ""
                page_title = ""
                try:
                    result_page = await self.get(link)
                    if result_page:
                        page_title = result_page.css("title::text").get("").strip()
                        content_selectors = ["article", ".article-content", ".post-content", ".entry-content", ".content", "#content", "main", ".main", "body"]
                        for selector in content_selectors:
                            content_elem = result_page.css(selector)
                            if content_elem:
                                texts = content_elem.css("::text").getall()
                                page_content = " ".join([t.strip() for t in texts if t.strip()])
                                if len(page_content) > 100:
                                    break
                        if len(page_content) > 2000:
                            page_content = page_content[:2000] + "..."
                except Exception as e:
                    page_content = f"Error: {str(e)}"
                yield {
                    "keyword": keyword,
                    "rank": i + 1,
                    "title": title,
                    "link": link,
                    "abstract": abstract_text,
                    "page_title": page_title,
                    "page_content": page_content,
                }