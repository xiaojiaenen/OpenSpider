"""爬虫执行器 — 管理单个爬虫的执行生命周期"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime

from loguru import logger

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

            # 创建 Scrapling session
            await self._create_session()
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
            await self._update_task_status(TaskStatus.FAILED, str(e))

        finally:
            await self._close_session()
            logger.info(
                f"爬虫结束: {spider.name} | "
                f"数据: {self.items_scraped} | "
                f"请求: {self.requests_made} | "
                f"错误: {self.errors_count}"
            )

    async def _create_session(self) -> None:
        """根据爬虫配置创建 Scrapling session"""
        from scrapling.fetchers import FetcherSession, AsyncStealthySession, AsyncDynamicSession

        if self.spider.use_stealth:
            self._session = AsyncStealthySession(
                headless=True,
                solve_cloudflare=self.spider.solve_cloudflare,
                block_webrtc=self.spider.block_webrtc,
                hide_canvas=self.spider.hide_canvas,
                allow_webgl=self.spider.allow_webgl,
                real_chrome=self.spider.real_chrome,
                cdp_url=self.spider.cdp_url,
                user_data_dir=self.spider.user_data_dir,
                max_pages=self.spider.max_pages,
                block_ads=self.spider.block_ads,
                dns_over_https=self.spider.dns_over_https,
                locale=self.spider.locale,
                timeout=self.spider.timeout * 1000,  # 毫秒
            )
        else:
            self._session = FetcherSession(
                impersonate=self.spider.impersonate,
                http3=self.spider.http3,
                stealthy_headers=self.spider.stealthy_headers,
                verify=self.spider.ssl_verify,
                timeout=self.spider.timeout,
            )

    async def _close_session(self) -> None:
        """关闭 Scrapling session"""
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
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
