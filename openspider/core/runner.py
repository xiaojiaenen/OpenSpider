"""爬虫执行器 — 管理单个爬虫的执行生命周期"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime

from loguru import logger

from openspider.core.recovery import RecoveryManager
from openspider.models.spider import SpiderStatus
from openspider.models.task import TaskStatus
from openspider.spiders.base import BaseSpider


class SpiderRunner:
    """爬虫执行器

    职责：
    - 创建 Scrapling session 并注入爬虫实例
    - 执行爬虫的 run() 方法，收集 yield 的数据项
    - 管理停止信号和优雅退出
    - 更新任务状态和统计数据
    """

    def __init__(self, spider_instance: BaseSpider, task_id: int, db_session_factory):
        self.spider = spider_instance
        self.task_id = task_id
        self.db_session_factory = db_session_factory
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._session = None

        # 统计
        self.items_scraped = 0
        self.requests_made = 0
        self.errors_count = 0
        self.retry_count = 0

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """启动爬虫执行"""
        self._task = asyncio.create_task(self._run())

    async def stop(self, timeout: float = 30.0) -> None:
        """发送停止信号，等待爬虫优雅退出"""
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

    async def _run(self) -> None:
        """执行爬虫的核心逻辑"""
        spider = self.spider
        logger.info(f"爬虫启动: {spider.name}")

        try:
            # 注入停止信号
            spider._stop_event = self._stop_event

            # 创建 Scrapling session（使用 async context manager）
            self._session_ctx = self._create_session_context()
            self._session = await self._session_ctx.__aenter__()
            spider._session = self._session

            # 调用 on_start 钩子
            await spider.on_start()

            # 执行 run()，收集数据项
            async for item in spider.run():
                if self._stop_event.is_set():
                    break

                # 后处理
                processed = await spider.on_item_scraped(item)
                if processed is not None:
                    await self._save_item(processed)
                    self.items_scraped += 1

            # 调用 on_complete 钩子
            await spider.on_complete()
            await self._update_task_status(TaskStatus.COMPLETED)

        except asyncio.CancelledError:
            logger.info(f"爬虫被取消: {spider.name}")
            await self._update_task_status(TaskStatus.PAUSED)

        except Exception as e:
            logger.error(f"爬虫异常: {spider.name}: {e}")
            self.errors_count += 1
            await spider.on_error(e)

            # 重试逻辑
            if self.retry_count < spider.max_retries:
                self.retry_count += 1
                backoff = RecoveryManager.calculate_backoff(
                    self.retry_count, spider.retry_delay
                )
                logger.info(
                    f"爬虫 {spider.name} 将在 {backoff}s 后重试 "
                    f"({self.retry_count}/{spider.max_retries})"
                )
                await self._update_task_status(TaskStatus.RUNNING, str(e))
                await asyncio.sleep(backoff)
                if not self._stop_event.is_set():
                    await self._run()  # 递归重试
                return

            await self._update_task_status(TaskStatus.FAILED, str(e))

        finally:
            await self._close_session()
            logger.info(
                f"爬虫结束: {spider.name} | "
                f"数据: {self.items_scraped} | "
                f"请求: {self.requests_made} | "
                f"错误: {self.errors_count}"
            )

    def _create_session_context(self):
        """根据爬虫配置创建 Scrapling session 的 async context manager"""
        from scrapling.fetchers import FetcherSession, AsyncStealthySession, AsyncDynamicSession
        from contextlib import asynccontextmanager

        spider = self.spider

        if spider.use_stealth:
            session = AsyncStealthySession(
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
                timeout=spider.timeout * 1000,  # 毫秒
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
            session = FetcherSession(
                impersonate=spider.impersonate,
                http3=spider.http3,
                stealthy_headers=spider.stealthy_headers,
                verify=spider.ssl_verify,
                timeout=spider.timeout,
            )
        return session

    async def _close_session(self) -> None:
        """关闭 Scrapling session"""
        if hasattr(self, '_session_ctx') and self._session_ctx is not None:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_ctx = None
        self._session = None

    async def _save_item(self, item: dict) -> None:
        """保存数据项到数据库"""
        from openspider.models.item import ItemModel

        async with self.db_session_factory() as session:
            db_item = ItemModel(
                spider_name=self.spider.name,
                task_id=self.task_id,
                data=item,
                url=item.get("url", ""),
            )
            session.add(db_item)
            await session.commit()

    async def _update_task_status(self, status: TaskStatus, error_message: str | None = None) -> None:
        """更新任务状态"""
        from openspider.models.task import TaskModel

        async with self.db_session_factory() as session:
            from sqlalchemy import select, update

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

        # 同步更新 spiders 表状态
        spider_status_map = {
            TaskStatus.COMPLETED: SpiderStatus.IDLE,
            TaskStatus.FAILED: SpiderStatus.FAILED,
            TaskStatus.PAUSED: SpiderStatus.PAUSED,
        }
        spider_status = spider_status_map.get(status)
        if spider_status:
            from openspider.models.spider import SpiderModel
            async with self.db_session_factory() as session:
                stmt = (
                    update(SpiderModel)
                    .where(SpiderModel.name == self.spider.name)
                    .values(status=spider_status)
                )
                await session.execute(stmt)
                await session.commit()
