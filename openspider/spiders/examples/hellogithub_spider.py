"""测试爬虫 — 爬取 HelloGitHub 开源项目数据"""

from openspider.spiders.base import BaseSpider


class HelloGitHubSpider(BaseSpider):
    """通过 API 爬取 hellogithub.com 开源项目数据"""

    name = "hellogithub"
    description = "爬取 HelloGitHub 开源项目推荐"
    start_urls = ["https://api.hellogithub.com/v1/search/?q=open+source&page=1"]

    # 数据 schema
    schema = {
        "rid": "string",
        "title": "string",
        "title_en": "string",
        "author": "string",
        "full_name": "string",
        "summary": "text",
        "summary_en": "text",
        "primary_lang": "string",
        "stars": "int",
        "publish_at": "string",
    }
    primary_key = ["rid"]

    # 翻页参数
    max_pages = 5

    async def run(self):
        keywords = ["python", "javascript", "rust", "go", "java"]
        for keyword in keywords:
            if self.should_stop:
                break
            for page_num in range(1, self.max_pages + 1):
                if self.should_stop:
                    break
                url = f"https://api.hellogithub.com/v1/search/?q={keyword}&page={page_num}"
                try:
                    resp = await self.get(url)
                    data = resp.json()
                    if not data.get("success"):
                        break
                    repos = data.get("data", [])
                    if not repos:
                        break
                    for repo in repos:
                        yield {
                            "rid": repo.get("rid", ""),
                            "title": repo.get("title", ""),
                            "title_en": repo.get("title_en", ""),
                            "author": repo.get("author", ""),
                            "full_name": repo.get("full_name", ""),
                            "summary": repo.get("summary", ""),
                            "summary_en": repo.get("summary_en", ""),
                            "primary_lang": repo.get("primary_lang", ""),
                            "stars": repo.get("stars", 0),
                            "publish_at": repo.get("publish_at", ""),
                        }
                    if not data.get("has_more"):
                        break
                except Exception as e:
                    await self.on_error(e)
                    break
