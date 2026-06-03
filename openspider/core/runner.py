"""爬虫执行器 — 委托 Scrapling Spider 处理爬取调度，平台管理生命周期"""

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

    职责：
    - 创建 Scrapling Spider 子类（运行时动态生成），复用其并发/去重/代理轮换
    - 管理爬虫生命周期（启动、停止、暂停恢复）
    - 统计数据和日志写入 MySQL
    - 失败重试与指数退避
    """

    def __init__(self, spider_instance: BaseSpider, task_id: int, db_session_factory):
        self.spider = spider_instance
        self.task_id = task_id
        self.db_session_factory = db_session_factory
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._scrapling_result = None

        # 统计
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
                log_entry = LogModel(
                    spider_name=self.spider.name,
                    task_id=self.task_id,
                    level=level,
                    message=message,
                )
                session.add(log_entry)
                await session.commit()
        except Exception:
            pass

    async def _run(self) -> None:
        spider = self.spider
        logger.info(f"爬虫启动: {spider.name}")
        await self._log(LogLevel.INFO, f"爬虫启动: {spider.name}")

        try:
            spider._stop_event = self._stop_event

            # 判断模式：是否重写了 parse()
            _has_custom_parse = type(spider).parse is not BaseSpider.parse

            if _has_custom_parse:
                # 高级模式：创建 Scrapling Spider 子类，委托其调度引擎
                await self._run_with_scrapling(spider)
            else:
                # 简单模式：run() 异步生成器
                await self._run_simple(spider)

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
                backoff = RecoveryManager.calculate_backoff(
                    self.retry_count, spider.retry_delay
                )
                logger.info(f"爬虫 {spider.name} 将在 {backoff}s 后重试 ({self.retry_count}/{spider.max_retries})")
                await self._log(LogLevel.WARNING, f"将在 {backoff}s 后重试 ({self.retry_count}/{spider.max_retries})")
                await self._update_task_status(TaskStatus.RUNNING, str(e))
                await asyncio.sleep(backoff)
                if not self._stop_event.is_set():
                    await self._run()
                return

            await self._log(LogLevel.ERROR, f"爬虫失败: {spider.name}, 已达最大重试次数")
            await self._update_task_status(TaskStatus.FAILED, str(e))

        finally:
            logger.info(
                f"爬虫结束: {spider.name} | "
                f"数据: {self.items_scraped} | "
                f"请求: {self.requests_made} | "
                f"错误: {self.errors_count}"
            )

    async def _run_simple(self, spider: BaseSpider) -> None:
        """简单模式：run() 异步生成器"""
        # 创建 session
        self._session = self._create_session()
        spider._session = self._session

        await spider.on_start()

        async for item in spider.run():
            if self._stop_event.is_set():
                break
            processed = await spider.on_item_scraped(item)
            if processed is not None:
                await self._save_item(processed)
                self.items_scraped += 1

        await self._close_session()

    async def _run_with_scrapling(self, spider: BaseSpider) -> None:
        """高级模式：创建 Scrapling Spider 子类，委托其调度引擎

        Scrapling 的 Spider 框架提供：
        - 并发请求（concurrent_requests）
        - 请求去重（内置 fingerprint）
        - 代理轮换（ProxyRotator）
        - 暂停恢复（crawldir）
        - 请求间隔（download_delay）
        - robots.txt 遵守
        """
        scrapling_spider_cls = self._create_scrapling_spider(spider)
        scrapling_spider = scrapling_spider_cls(crawldir=str(self._get_crawldir()))

        await spider.on_start()

        # Scrapling Spider.start() 是同步阻塞的，放到线程池执行
        result = await asyncio.to_thread(scrapling_spider.start)
        self._scrapling_result = result

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
        """动态创建 Scrapling Spider 子类，转发用户配置"""
        from scrapling.spiders import Spider, Request, Response

        base_spider = spider

        class DynamicSpider(Spider):
            name = base_spider.name
            start_urls = base_spider.start_urls
            concurrent_requests = base_spider.concurrent_requests
            download_delay = base_spider.download_delay
            robots_txt_obey = base_spider.robots_txt_obey
            development_mode = base_spider.development_mode

            async def parse(self_inner, response: Response):
                """桥接：调用用户的 parse()，收集 yield 的结果"""
                async for result in base_spider.parse(response):
                    yield result

        return DynamicSpider

    def _create_session(self):
        """简单模式下创建 Scrapling session"""
        from scrapling.fetchers import FetcherSession, AsyncStealthySession

        spider = self.spider
        if spider.use_stealth:
            return AsyncStealthySession(
                headless=True,
                solve_cloudflare=spider.solve_cloudflare,
                block_webrtc=spider.block_webrtc,
                hide_canvas=spider.hide_canvas,
                allow_webgl=spider.allow_webgl,
                real_chrome=spider.real_chrome,
                cdp_url=spider.cdp_url,
                user_data_dir=spider.user_data_dir,
                max_pages=spider.max_pages,
                block_ads=spider.block_ads,
                dns_over_https=spider.dns_over_https,
                locale=spider.locale,
                timezone_id=spider.timezone_id,
                timeout=spider.timeout * 1000,
                wait=spider.wait,
                disable_resources=spider.disable_resources,
                network_idle=spider.network_idle,
                load_dom=spider.load_dom,
                wait_selector=spider.wait_selector,
                wait_selector_state=spider.wait_selector_state,
                init_script=spider.init_script,
                capture_xhr=spider.capture_xhr,
            )
        else:
            return FetcherSession(
                impersonate=spider.impersonate,
                http3=spider.http3,
                stealthy_headers=spider.stealthy_headers,
                verify=spider.ssl_verify,
                timeout=spider.timeout,
            )

    async def _close_session(self) -> None:
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

    def _get_crawldir(self):
        from openspider.config import settings
        return settings.crawl_data_dir / self.spider.name

    async def _save_item(self, item: dict) -> None:
        from openspider.models.item import ItemModel
        try:
            async with self.db_session_factory() as session:
                db_item = ItemModel(
                    spider_name=self.spider.name,
                    task_id=self.task_id,
                    data=item,
                    url=item.get("url", ""),
                )
                session.add(db_item)
                await session.commit()
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    async def _update_task_status(self, status: TaskStatus, error_message: str | None = None) -> None:
        from openspider.models.task import TaskModel
        from openspider.models.spider import SpiderModel
        from sqlalchemy import update

        async with self.db_session_factory() as session:
            stmt = (
                update(TaskModel)
                .where(TaskModel.id == self.task_id)
                .values(
                    status=status,
                    items_scraped=self.items_scraped,
                    requests_made=self.requests_made,
                    errors_count=self.errors_count,
                    error_message=error_message,
                    finished_at=datetime.utcnow() if status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else None,
                )
            )
            await session.execute(stmt)
            await session.commit()

        spider_status_map = {
            TaskStatus.COMPLETED: SpiderStatus.IDLE,
            TaskStatus.FAILED: SpiderStatus.FAILED,
            TaskStatus.PAUSED: SpiderStatus.PAUSED,
        }
        spider_status = spider_status_map.get(status)
        if spider_status:
            async with self.db_session_factory() as session:
                stmt = (
                    update(SpiderModel)
                    .where(SpiderModel.name == self.spider.name)
                    .values(status=spider_status)
                )
                await session.execute(stmt)
                await session.commit()
