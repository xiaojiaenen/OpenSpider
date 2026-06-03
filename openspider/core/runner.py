"""爬虫执行器 — 统一委托 Scrapling Spider，不再造轮子"""

from __future__ import annotations

import asyncio
from datetime import datetime

from loguru import logger

from openspider.core.recovery import RecoveryManager
from openspider.models.log import LogModel, LogLevel
from openspider.models.spider import SpiderStatus
from openspider.models.task import TaskStatus
from openspider.spiders.base import BaseSpider


class SpiderRunner:
    """爬虫执行器

    统一通过 Scrapling Spider 执行爬取，复用其：
    - 并发请求（concurrent_requests）
    - 请求去重（内置 fingerprint）
    - 代理轮换（ProxyRotator via configure_sessions）
    - 暂停恢复（crawldir）
    - 请求间隔（download_delay）
    - robots.txt 遵守
    - 浏览器 session 管理（Stealthy/Dynamic）
    """

    def __init__(self, spider_instance: BaseSpider, task_id: int, db_session_factory):
        self.spider = spider_instance
        self.task_id = task_id
        self.db_session_factory = db_session_factory
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

        self.items_scraped = 0
        self.requests_made = 0
        self.errors_count = 0
        self.retry_count = 0

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self, timeout: float = 30.0) -> None:
        logger.info(f"发送停止信号: {self.spider.name}")
        self._stop_event.set()
        self.spider._stop_event = self._stop_event

        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"爬虫 {self.spider.name} 超时未退出，强制取消")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

    async def _log(self, level: LogLevel, message: str) -> None:
        try:
            async with self.db_session_factory() as session:
                session.add(LogModel(
                    spider_name=self.spider.name,
                    task_id=self.task_id,
                    level=level,
                    message=message,
                ))
                await session.commit()
        except Exception:
            pass

    async def _run(self) -> None:
        spider = self.spider
        logger.info(f"爬虫启动: {spider.name}")
        await self._log(LogLevel.INFO, f"爬虫启动: {spider.name}")

        try:
            spider._stop_event = self._stop_event
            await spider.on_start()

            # 统一走 Scrapling Spider
            await self._run_with_scrapling(spider)

            await spider.on_complete()
            await self._log(LogLevel.INFO, f"爬虫完成: {spider.name}, 数据: {self.items_scraped}")
            await self._update_task_status(TaskStatus.COMPLETED)

        except asyncio.CancelledError:
            logger.info(f"爬虫被取消: {spider.name}")
            await self._log(LogLevel.WARNING, f"爬虫被取消: {spider.name}")
            await self._update_task_status(TaskStatus.PAUSED)

        except Exception as e:
            logger.error(f"爬虫异常: {spider.name}: {e}")
            self.errors_count += 1
            await self._log(LogLevel.ERROR, f"爬虫异常: {spider.name}: {e}")
            await spider.on_error(e)

            if self.retry_count < spider.max_retries:
                self.retry_count += 1
                backoff = RecoveryManager.calculate_backoff(self.retry_count, spider.retry_delay)
                await self._log(LogLevel.WARNING, f"将在 {backoff}s 后重试 ({self.retry_count}/{spider.max_retries})")
                await self._update_task_status(TaskStatus.RUNNING, str(e))
                await asyncio.sleep(backoff)
                if not self._stop_event.is_set():
                    await self._run()
                return

            await self._log(LogLevel.ERROR, f"爬虫失败: {spider.name}, 已达最大重试次数")
            await self._update_task_status(TaskStatus.FAILED, str(e))

        finally:
            logger.info(f"爬虫结束: {spider.name} | 数据: {self.items_scraped} | 请求: {self.requests_made} | 错误: {self.errors_count}")

    async def _run_with_scrapling(self, spider: BaseSpider) -> None:
        """统一通过 Scrapling Spider 执行

        简单模式：run() 包装为 parse()
        高级模式：直接用用户的 parse()
        """
        scrapling_spider_cls = self._create_scrapling_spider(spider)
        scrapling_spider = scrapling_spider_cls(crawldir=str(self._get_crawldir()))

        # Scrapling Spider.start() 是同步阻塞的，放到线程池
        result = await asyncio.to_thread(scrapling_spider.start)

        # 收集结果
        if hasattr(result, 'items'):
            for item_data in result.items:
                if self._stop_event.is_set():
                    break
                if isinstance(item_data, dict):
                    processed = await spider.on_item_scraped(item_data)
                    if processed is not None:
                        await self._save_item(processed)
                        self.items_scraped += 1

        self.requests_made = getattr(result, 'total_requests', 0) or self.requests_made

    def _create_scrapling_spider(self, spider: BaseSpider):
        """动态创建 Scrapling Spider 子类

        转发所有配置：Spider 属性 + Session 配置（via configure_sessions）
        """
        from scrapling.spiders import Spider, Response
        from scrapling.fetchers import FetcherSession, AsyncStealthySession, ProxyRotator

        base_spider = spider
        _has_custom_parse = type(spider).parse is not BaseSpider.parse

        # 构建 session 参数
        session_kwargs = {
            "impersonate": spider.impersonate,
            "http3": spider.http3,
            "stealthy_headers": spider.stealthy_headers,
            "verify": spider.ssl_verify,
            "timeout": spider.timeout,
        }
        if spider.default_headers:
            session_kwargs["headers"] = spider.default_headers
        if spider.cookies:
            session_kwargs["cookies"] = spider.cookies
        if spider.follow_redirects is False:
            session_kwargs["follow_redirects"] = False

        # 代理轮换
        proxy_rotator = None
        if spider.proxies:
            if len(spider.proxies) > 1:
                proxy_rotator = ProxyRotator(spider.proxies)
            else:
                session_kwargs["proxy"] = spider.proxies[0]

        # 浏览器 session 配置
        stealth_kwargs = {
            "headless": True,
            "solve_cloudflare": spider.solve_cloudflare,
            "block_webrtc": spider.block_webrtc,
            "hide_canvas": spider.hide_canvas,
            "allow_webgl": spider.allow_webgl,
            "real_chrome": spider.real_chrome,
            "cdp_url": spider.cdp_url,
            "user_data_dir": spider.user_data_dir,
            "max_pages": spider.max_pages,
            "block_ads": spider.block_ads,
            "dns_over_https": spider.dns_over_https,
            "locale": spider.locale,
            "timezone_id": spider.timezone_id,
            "wait": spider.wait,
            "disable_resources": spider.disable_resources,
            "network_idle": spider.network_idle,
            "load_dom": spider.load_dom,
            "wait_selector": spider.wait_selector,
            "wait_selector_state": spider.wait_selector_state,
            "init_script": spider.init_script,
            "capture_xhr": spider.capture_xhr,
        }

        class DynamicSpider(Spider):
            name = base_spider.name
            start_urls = base_spider.start_urls
            concurrent_requests = base_spider.concurrent_requests
            download_delay = base_spider.download_delay
            robots_txt_obey = base_spider.robots_txt_obey
            development_mode = base_spider.development_mode

            def configure_sessions(self_inner, manager):
                """配置 Scrapling session，转发用户的所有配置"""
                if base_spider.use_stealth:
                    sess = AsyncStealthySession(**stealth_kwargs)
                else:
                    sess = FetcherSession(**session_kwargs)

                if proxy_rotator:
                    # 代理轮换注入到 session
                    if base_spider.use_stealth:
                        stealth_kwargs["proxy_rotator"] = proxy_rotator
                    else:
                        session_kwargs["proxy_rotator"] = proxy_rotator

                manager.add("default", sess)

            async def parse(self_inner, response: Response):
                if _has_custom_parse:
                    # 高级模式：直接调用用户的 parse()
                    async for result in base_spider.parse(response):
                        yield result
                else:
                    # 简单模式：调用用户的 run()，把 response 注入
                    base_spider._scrapling_response = response
                    # 简单模式下 run() 需要 session，注入 Scrapling 的 session
                    base_spider._session = self_inner._session
                    async for result in base_spider.run():
                        yield result

        return DynamicSpider

    def _get_crawldir(self):
        from openspider.config import settings
        return settings.crawl_data_dir / self.spider.name

    async def _save_item(self, item: dict) -> None:
        from openspider.models.item import ItemModel
        try:
            async with self.db_session_factory() as session:
                session.add(ItemModel(
                    spider_name=self.spider.name,
                    task_id=self.task_id,
                    data=item,
                    url=item.get("url", ""),
                ))
                await session.commit()
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    async def _update_task_status(self, status: TaskStatus, error_message: str | None = None) -> None:
        from openspider.models.task import TaskModel
        from openspider.models.spider import SpiderModel
        from sqlalchemy import update

        async with self.db_session_factory() as session:
            await session.execute(
                update(TaskModel).where(TaskModel.id == self.task_id).values(
                    status=status,
                    items_scraped=self.items_scraped,
                    requests_made=self.requests_made,
                    errors_count=self.errors_count,
                    error_message=error_message,
                    finished_at=datetime.utcnow() if status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else None,
                )
            )
            await session.commit()

        spider_status_map = {
            TaskStatus.COMPLETED: SpiderStatus.IDLE,
            TaskStatus.FAILED: SpiderStatus.FAILED,
            TaskStatus.PAUSED: SpiderStatus.PAUSED,
        }
        spider_status = spider_status_map.get(status)
        if spider_status:
            async with self.db_session_factory() as session:
                await session.execute(
                    update(SpiderModel).where(SpiderModel.name == self.spider.name).values(status=spider_status)
                )
                await session.commit()
