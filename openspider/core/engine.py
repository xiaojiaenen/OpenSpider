"""核心引擎 — 协调注册表、执行器、调度器"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from openspider.config import settings
from openspider.core.registry import SpiderRegistry
from openspider.core.recovery import RecoveryManager
from openspider.core.runner import SpiderRunner
from openspider.core.scheduler import SpiderScheduler
from openspider.models.spider import SpiderModel, SpiderStatus
from openspider.models.task import TaskModel, TaskStatus
from openspider.storage.database import async_session


class Engine:
    """核心引擎

    职责：
    - 初始化注册表和文件监控
    - 管理运行中的爬虫实例
    - 提供爬虫启停接口供 API/CLI 调用
    """

    def __init__(self):
        self.registry = SpiderRegistry(settings.spiders_dir)
        self.scheduler = SpiderScheduler(self)
        self.recovery = RecoveryManager()
        self._runners: dict[str, SpiderRunner] = {}  # spider_name -> runner
        self._file_observer = None

    async def initialize(self) -> None:
        """初始化引擎：扫描爬虫、同步数据库、启动调度器和文件监控"""
        from openspider.storage.database import init_db
        await init_db()

        # 扫描爬虫目录
        count = self.registry.scan_directory()
        logger.info(f"扫描到 {count} 个爬虫")

        # 同步到数据库
        await self._sync_spiders_to_db()

        # 崩溃恢复
        crashed = await self.recovery.check_crashed_tasks()
        if crashed:
            logger.warning(f"发现 {len(crashed)} 个崩溃任务")

        # 启动调度器并同步定时任务
        self.scheduler.start()
        await self.scheduler.sync_schedules()

        # 启动文件监控
        self._start_file_watcher()

    async def shutdown(self) -> None:
        """关闭引擎：停止调度器、停止所有爬虫、关闭文件监控"""
        self.scheduler.shutdown()
        for name in list(self._runners.keys()):
            await self.stop_spider(name)
        self._stop_file_watcher()
        from openspider.storage.database import close_db
        await close_db()

    async def start_spider(self, name: str, params: dict | None = None) -> TaskModel:
        """启动爬虫

        Args:
            name: 爬虫名称
            params: 运行时参数（通过 API/CLI 传入）

        Raises:
            ValueError: 爬虫不存在或已在运行
        """
        if name in self._runners and self._runners[name].is_running:
            raise ValueError(f"爬虫 {name} 已在运行")

        spider_cls = self.registry.get(name)
        if spider_cls is None:
            raise ValueError(f"爬虫 {name} 不存在")

        # 创建任务记录
        async with async_session() as session:
            task = TaskModel(spider_name=name, status=TaskStatus.RUNNING, params=params or {})
            session.add(task)
            await session.commit()
            await session.refresh(task)
            task_id = task.id

        # 更新爬虫状态
        async with async_session() as session:
            from sqlalchemy import update
            stmt = (
                update(SpiderModel)
                .where(SpiderModel.name == name)
                .values(status=SpiderStatus.RUNNING)
            )
            await session.execute(stmt)
            await session.commit()

        # 创建并启动执行器
        spider_instance = spider_cls()
        spider_instance.params = params or {}
        runner = SpiderRunner(spider_instance, task_id, async_session)
        self._runners[name] = runner
        await runner.start()

        logger.info(f"爬虫已启动: {name}, 任务ID: {task_id}")
        return task

    async def stop_spider(self, name: str) -> bool:
        """停止爬虫

        Returns:
            是否成功停止
        """
        runner = self._runners.get(name)
        if runner is None or not runner.is_running:
            return False

        await runner.stop()
        logger.info(f"爬虫已停止: {name}")
        return True

    async def pause_spider(self, name: str) -> bool:
        """暂停爬虫（同 stop，保留断点）"""
        return await self.stop_spider(name)

    def get_spider_status(self, name: str) -> dict | None:
        """获取爬虫运行状态"""
        spider_cls = self.registry.get(name)
        if spider_cls is None:
            return None

        runner = self._runners.get(name)
        return {
            "name": name,
            "description": getattr(spider_cls, "description", ""),
            "is_running": runner.is_running if runner else False,
            "items_scraped": runner.items_scraped if runner else 0,
            "requests_made": runner.requests_made if runner else 0,
            "errors_count": runner.errors_count if runner else 0,
        }

    async def _sync_spiders_to_db(self) -> None:
        """将注册表中的爬虫同步到数据库"""
        async with async_session() as session:
            from sqlalchemy import select
            for name, cls in self.registry.spiders.items():
                result = await session.execute(
                    select(SpiderModel).where(SpiderModel.name == name)
                )
                existing = result.scalar_one_or_none()
                if existing is None:
                    db_spider = SpiderModel(
                        name=name,
                        description=getattr(cls, "description", ""),
                        file_path=str(settings.spiders_dir / f"{name}.py"),
                        schedule=getattr(cls, "schedule", None),
                        max_retries=getattr(cls, "max_retries", 3),
                        retry_delay=getattr(cls, "retry_delay", 60),
                        status=SpiderStatus.IDLE,
                    )
                    session.add(db_spider)
            await session.commit()

    def _start_file_watcher(self) -> None:
        """启动文件监控"""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

            class SpiderFileHandler(FileSystemEventHandler):
                def __init__(self, registry: SpiderRegistry):
                    self.registry = registry

                def on_created(self, event):
                    if not event.is_directory and event.src_path.endswith(".py"):
                        logger.info(f"检测到新爬虫文件: {event.src_path}")
                        try:
                            self.registry.register_file(Path(event.src_path))
                        except Exception as e:
                            logger.error(f"热加载失败: {e}")

                def on_modified(self, event):
                    if not event.is_directory and event.src_path.endswith(".py"):
                        logger.info(f"检测到爬虫文件变更: {event.src_path}")
                        try:
                            self.registry.register_file(Path(event.src_path))
                        except Exception as e:
                            logger.error(f"热加载失败: {e}")

            self._file_observer = Observer()
            handler = SpiderFileHandler(self.registry)
            self._file_observer.schedule(handler, str(settings.spiders_dir), recursive=True)
            self._file_observer.daemon = True
            self._file_observer.start()
            logger.info(f"文件监控已启动: {settings.spiders_dir}")
        except Exception as e:
            logger.warning(f"文件监控启动失败: {e}")

    def _stop_file_watcher(self) -> None:
        """停止文件监控"""
        if self._file_observer is not None:
            self._file_observer.stop()
            self._file_observer = None
