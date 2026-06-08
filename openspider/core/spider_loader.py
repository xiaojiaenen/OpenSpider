"""爬虫加载器 — 在沙箱子进程中加载并运行 BaseSpider

这个模块由子进程 import 执行，负责：
1. 加载爬虫 .py 文件
2. 找到 BaseSpider 子类
3. 运行 spider.run()，将结果通过 queue 回传给主进程
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from loguru import logger


def _load_spider_class(code_path: str) -> type:
    """加载爬虫文件，返回 BaseSpider 子类"""
    from openspider.spiders.base import BaseSpider

    module_name = f"_sandboxed_spider_{Path(code_path).stem}"
    spec = importlib.util.spec_from_file_location(module_name, code_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载文件: {code_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # 查找 BaseSpider 子类
    spider_cls = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseSpider)
            and attr is not BaseSpider
            and not attr_name.startswith("_")
        ):
            spider_cls = attr
            break

    if spider_cls is None:
        raise RuntimeError(f"未找到 BaseSpider 子类: {code_path}")

    return spider_cls


def _build_session_kwargs(spider) -> dict:
    """从爬虫配置构建 FetcherSession 参数"""
    kwargs = {
        "impersonate": spider.impersonate,
        "http3": spider.http3,
        "stealthy_headers": spider.stealthy_headers,
        "verify": spider.ssl_verify,
        "timeout": spider.timeout,
    }
    if spider.default_headers:
        kwargs["headers"] = spider.default_headers
    if spider.cookies:
        kwargs["cookies"] = spider.cookies
    if spider.follow_redirects is False:
        kwargs["follow_redirects"] = False
    return kwargs


async def run_spider_in_subprocess(
    code_path: str,
    args: dict,
    queue,  # multiprocessing.Queue
    stop_event,  # multiprocessing.Event
    batch_size: int = 100,
):
    """子进程中运行爬虫的入口函数

    Args:
        code_path: 爬虫 .py 文件的绝对路径
        args: 运行时参数 (params, user_id 等)
        queue: 结果回传队列，消息格式 {"type": "items"|"done"|"error", ...}
        stop_event: 停止信号
        batch_size: 每批回传多少条数据
    """
    try:
        spider_cls = _load_spider_class(code_path)
        spider = spider_cls()
        spider.params = args.get("params", {})

        # 设置 FetcherSession
        from scrapling.fetchers import FetcherSession, ProxyRotator

        session_kwargs = _build_session_kwargs(spider)

        # 代理轮换
        if spider.proxies:
            if len(spider.proxies) > 1:
                session_kwargs["proxy_rotator"] = ProxyRotator(spider.proxies)
            else:
                session_kwargs["proxy"] = spider.proxies[0]

        session_ctx = FetcherSession(**session_kwargs)
        session = session_ctx.__enter__()
        spider._session = session

        try:
            # 检查是否使用 Scrapling 高级模式
            from openspider.spiders.base import BaseSpider
            _has_custom_parse = type(spider).parse is not BaseSpider.parse

            if _has_custom_parse or spider.development_mode:
                await _run_with_scrapling(spider, queue, stop_event, batch_size)
            else:
                await _run_simple(spider, queue, stop_event, batch_size)
        finally:
            session_ctx.__exit__(None, None, None)

        if not stop_event.is_set():
            queue.put({"type": "done"})

    except Exception as e:
        logger.error(f"沙箱子进程异常: {e}")
        queue.put({"type": "error", "message": str(e)})


async def _run_simple(spider, queue, stop_event, batch_size: int):
    """简单模式：直接跑 run()"""
    batch: list[dict] = []
    try:
        async for item in spider.run():
            if stop_event.is_set():
                break
            if isinstance(item, dict):
                processed = await spider.on_item_scraped(item)
                if processed is not None:
                    batch.append(processed)
                    if len(batch) >= batch_size:
                        queue.put({"type": "items", "data": batch})
                        batch = []
    finally:
        if batch:
            queue.put({"type": "items", "data": batch})


async def _run_with_scrapling(spider, queue, stop_event, batch_size: int):
    """高级模式：通过 Scrapling Spider 执行"""
    import asyncio

    from openspider.core.scrapling_utils import create_scrapling_spider
    from openspider.config import settings

    scrapling_spider_cls = create_scrapling_spider(spider)
    crawldir = str(settings.crawl_data_dir / spider.name)
    scrapling_spider = scrapling_spider_cls(crawldir=crawldir)

    # Scrapling Spider.start() 是同步阻塞的
    result = await asyncio.to_thread(scrapling_spider.start)

    batch: list[dict] = []
    if hasattr(result, "items"):
        for item_data in result.items:
            if stop_event.is_set():
                break
            if isinstance(item_data, dict):
                processed = await spider.on_item_scraped(item_data)
                if processed is not None:
                    batch.append(processed)
                    if len(batch) >= batch_size:
                        queue.put({"type": "items", "data": batch})
                        batch = []

    if batch:
        queue.put({"type": "items", "data": batch})
