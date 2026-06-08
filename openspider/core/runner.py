"""爬虫执行器 — 协调沙箱执行、数据管道、任务状态

职责：
- 通过沙箱子进程执行爬虫代码（不再在主进程中执行）
- 管理数据管道（Pipeline）和数据保存
- 记录日志、更新任务状态、处理重试
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger

from openspider.core.recovery import RecoveryManager
from openspider.models.log import LogModel, LogLevel
from openspider.models.spider import SpiderStatus
from openspider.models.task import TaskStatus


class SpiderRunner:
    """爬虫执行器（沙箱模式）

    爬虫代码在子进程中执行，主进程只负责：
    - 调度执行（超时、重试）
    - 数据管道（接收数据 → 保存 → 分发到 Sink）
    - 任务状态管理
    """

    def __init__(
        self,
        spider_name: str,
        spider_file_path: str,
        task_id: int,
        db_session_factory,
        spider_attrs: dict | None = None,
        user_id: str | None = None,
    ):
        self.spider_name = spider_name
        self.spider_file_path = spider_file_path
        self.task_id = task_id
        self.db_session_factory = db_session_factory
        self._user_id = user_id
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._sandbox_gen = None  # 沙箱 async generator 引用

        # 爬虫元数据（从 registry 获取，不需要实例化）
        attrs = spider_attrs or {}
        self.max_retries = attrs.get("max_retries", 3)
        self.retry_delay = attrs.get("retry_delay", 60)
        self.sandbox_timeout = attrs.get("sandbox_timeout", 600)

        # 计数器
        self.items_scraped = 0
        self.requests_made = 0
        self.errors_count = 0
        self.retry_count = 0

        # SpiderDataManager 延迟初始化
        self._data_manager = None
        self._dm_initialized = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self, timeout: float = 30.0) -> None:
        logger.info(f"发送停止信号: {self.spider_name}")
        self._stop_event.set()

        # 关闭沙箱 generator（会触发子进程终止）
        if self._sandbox_gen is not None:
            try:
                await self._sandbox_gen.aclose()
            except Exception:
                pass

        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if not self._task.done():
                    logger.warning(f"爬虫 {self.spider_name} 超时未退出，强制取消")
                    self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _log(self, level: LogLevel, message: str) -> None:
        try:
            async with self.db_session_factory() as session:
                session.add(LogModel(
                    spider_name=self.spider_name,
                    task_id=self.task_id,
                    level=level,
                    message=message,
                ))
                await session.commit()
        except Exception as e:
            logger.warning(f"日志写入失败: {e}")

    async def _run(self) -> None:
        """主执行循环 — 通过沙箱运行爬虫"""
        logger.info(f"爬虫启动: {self.spider_name}")
        await self._log(LogLevel.INFO, f"爬虫启动: {self.spider_name}")

        # 初始化数据管道（不依赖爬虫实例）
        from openspider.core.pipeline import Pipeline
        pipeline = Pipeline.from_config(
            spider_name=self.spider_name,
            user_id=self._user_id,
        )
        await pipeline.open()

        try:
            # 通过沙箱子进程执行爬虫
            from openspider.core.sandbox_runner import run_sandboxed

            self._sandbox_gen = run_sandboxed(
                code_path=self.spider_file_path,
                args={"params": {}, "user_id": self._user_id},
            )

            async for item in self._sandbox_gen:
                if self._stop_event.is_set():
                    break
                if isinstance(item, dict):
                    await self._save_item(item)
                    await pipeline.process(item)
                    self.items_scraped += 1

            self._sandbox_gen = None

            await pipeline.flush()
            await self._log(LogLevel.INFO, f"爬虫完成: {self.spider_name}, 数据: {self.items_scraped}")
            await self._update_task_status(TaskStatus.COMPLETED)

        except asyncio.CancelledError:
            logger.info(f"爬虫被取消: {self.spider_name}")
            await self._log(LogLevel.WARNING, f"爬虫被取消: {self.spider_name}")
            await self._update_task_status(TaskStatus.PAUSED)

        except TimeoutError as e:
            logger.error(f"爬虫超时: {self.spider_name}: {e}")
            self.errors_count += 1
            await self._log(LogLevel.ERROR, f"爬虫超时: {self.spider_name}: {e}")
            await self._update_task_status(TaskStatus.FAILED, str(e))

        except Exception as e:
            logger.error(f"爬虫异常: {self.spider_name}: {e}")
            self.errors_count += 1
            await self._log(LogLevel.ERROR, f"爬虫异常: {self.spider_name}: {e}")

            # 重试逻辑
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                backoff = RecoveryManager.calculate_backoff(self.retry_count, self.retry_delay)
                await self._log(LogLevel.WARNING, f"将在 {backoff}s 后重试 ({self.retry_count}/{self.max_retries})")
                await self._update_task_status(TaskStatus.RUNNING, str(e))
                await asyncio.sleep(backoff)
                if not self._stop_event.is_set():
                    await self._run()
                return

            await self._log(LogLevel.ERROR, f"爬虫失败: {self.spider_name}, 已达最大重试次数")
            await self._update_task_status(TaskStatus.FAILED, str(e))

        finally:
            await pipeline.close()
            logger.info(
                f"爬虫结束: {self.spider_name} | "
                f"数据: {self.items_scraped} | 错误: {self.errors_count}"
            )

    # ── 数据管理 ──────────────────────────────────────────

    async def _get_or_init_data_manager(self):
        """懒加载 SpiderDataManager（仅当 spider 定义了 fields 时使用）"""
        if self._dm_initialized:
            return self._data_manager

        self._dm_initialized = True

        # 从数据库读取爬虫的 fields 定义
        from openspider.models.spider import SpiderModel
        from sqlalchemy import select

        async with self.db_session_factory() as session:
            result = await session.execute(
                select(SpiderModel).where(SpiderModel.name == self.spider_name)
            )
            db_spider = result.scalar_one_or_none()

        if db_spider is None:
            return None

        # 沙箱模式下 fields 从 DB 或注册表获取
        # 如果 DB 中没有 fields 配置，跳过 DataManager
        fields = getattr(db_spider, "fields", None) or []
        if not fields:
            return None

        from openspider.core.data_manager import SpiderDataManager
        dm = SpiderDataManager(
            db_session_factory=self.db_session_factory,
            spider_id=db_spider.id,
            spider_name=self.spider_name,
            fields=fields,
            dedup_key=getattr(db_spider, "dedup_key", None),
        )
        await dm.ensure_table()
        self._data_manager = dm
        return dm

    async def _save_item(self, item: dict) -> None:
        """保存数据项"""
        try:
            dm = await self._get_or_init_data_manager()
            if dm is not None:
                await dm.save_item(
                    item=item,
                    user_id=self._user_id or "",
                    task_id=self.task_id,
                )
            else:
                from openspider.models.item import ItemModel
                async with self.db_session_factory() as session:
                    session.add(ItemModel(
                        spider_name=self.spider_name,
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
                    finished_at=datetime.now() if status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else None,
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
                    update(SpiderModel).where(SpiderModel.name == self.spider_name).values(status=spider_status)
                )
                await session.commit()
