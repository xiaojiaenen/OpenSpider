"""页面交互示例爬虫

演示 Scrapling 的 page_action / page_setup 能力：
在浏览器加载页面后执行自定义 JavaScript 操作，
如滚动加载更多、点击按钮、填写表单等。
"""

from openspider.spiders.base import BaseSpider


async def scroll_to_bottom(page):
    """page_action 示例：滚动到页面底部以触发懒加载

    Scrapling 的 StealthyFetcher 会在页面加载后执行此函数。
    page 是 Playwright 的 Page 对象。
    """
    try:
        # 滚动到页面底部
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        # 等待内容加载
        await page.wait_for_timeout(2000)
        # 再次滚动以确保加载更多
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
    except Exception:
        pass


async def close_popups(page):
    """page_setup 示例：关闭弹窗和 Cookie 同意框

    在页面加载前或加载后立即执行。
    """
    try:
        # 常见的 Cookie 同意按钮
        for selector in [
            "#onetrust-accept-btn-handler",
            ".cookie-accept",
            "[data-testid='cookie-policy-manage-dialog-btn-accept']",
        ]:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0:
                    await btn.click(timeout=2000)
                    break
            except Exception:
                continue
    except Exception:
        pass


class InfiniteScrollSpider(BaseSpider):
    """无限滚动示例

    演示如何用 page_action 滚动加载更多内容。
    适用于瀑布流、时间线等无限滚动页面。

    使用方式：
        子类只需设置 page_action 为滚动函数，
        Scrapling 会在页面加载后自动执行。
    """
    name = "infinite_scroll_demo"
    description = "无限滚动示例 — page_action 滚动加载"
    start_urls = ["https://quotes.toscrape.com/scroll"]
    use_stealth = True
    network_idle = True
    wait = 2000  # 额外等待 2 秒

    # 设置页面交互钩子
    page_action = scroll_to_bottom

    async def run(self):
        """抓取滚动加载后的完整内容"""
        page = await self.get(self.start_urls[0])
        if not page:
            return

        for quote in page.css(".quote"):
            if self.should_stop:
                break
            yield {
                "text": quote.css(".text::text").get(""),
                "author": quote.css(".author::text").get(""),
                "tags": quote.css(".tag::text").getall(),
            }


class PopupHandlingSpider(BaseSpider):
    """弹窗处理示例

    演示 page_setup 关闭弹窗后再抓取内容。
    """
    name = "popup_handling_demo"
    description = "弹窗处理示例 — page_setup 关闭弹窗"
    start_urls = ["https://example.com"]
    use_stealth = True

    # 先关闭弹窗
    page_setup = close_popups

    async def run(self):
        page = await self.get(self.start_urls[0])
        if not page:
            return
        yield {
            "url": page.url if hasattr(page, 'url') else self.start_urls[0],
            "title": page.css("title::text").get(""),
        }
