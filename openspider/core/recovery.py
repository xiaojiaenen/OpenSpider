"""失败恢复 — 运行时重试、指数退避、崩溃恢复"""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select, update

from openspider.models.spider import SpiderModel, SpiderStatus
from openspider.models.task import TaskModel, TaskStatus
from openspider.storage.database import async_session


class RecoveryManager:
    """失败恢复管理器

    职责：
    - 运行时重试：爬虫执行过程中抛异常，按 max_retries × retry_delay 自动重试
    - 指数退避：连续失败时退避间隔翻倍，上限 1 小时
    - 崩溃恢复：平台重启后，检查状态为 running 的任务，标记为 crashed
    """

    MAX_BACKOFF = 3600  # 最大退避间隔（秒）

    async def check_crashed_tasks(self) -> list[dict]:
        """检查崩溃的任务，标记为 crashed 并返回列表

        Returns:
            崩溃任务列表
        """
        crashed = []
        async with async_session() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.status == TaskStatus.RUNNING)
            )
            tasks = result.scalars().all()

            for task in tasks:
                task.status = TaskStatus.CRASHED
                crashed.append({
                    "task_id": task.id,
                    "spider_name": task.spider_name,
                    "started_at": str(task.started_at) if task.started_at else None,
                })

                # 同步更新爬虫状态
                await session.execute(
                    update(SpiderModel)
                    .where(SpiderModel.name == task.spider_name)
                    .values(status=SpiderStatus.FAILED)
                )

            await session.commit()

        if crashed:
            logger.warning(f"发现 {len(crashed)} 个崩溃任务: {[c['spider_name'] for c in crashed]}")
        return crashed

    async def auto_restart_crashed(self, engine) -> int:
        """自动重启崩溃的爬虫

        Args:
            engine: 引擎实例

        Returns:
            重启的爬虫数量
        """
        crashed = await self.check_crashed_tasks()
        restarted = 0

        for task_info in crashed:
            spider_name = task_info["spider_name"]
            spider_cls = engine.registry.get(spider_name)
            if spider_cls is None:
                continue

            # 检查爬虫是否配置了自动重启
            if not getattr(spider_cls, "auto_restart", False):
                continue

            try:
                await engine.start_spider(spider_name)
                restarted += 1
                logger.info(f"自动重启爬虫: {spider_name}")
            except Exception as e:
                logger.error(f"自动重启失败: {spider_name}: {e}")

        return restarted

    @staticmethod
    def calculate_backoff(retry_count: int, base_delay: int) -> int:
        """计算指数退避间隔

        Args:
            retry_count: 已重试次数
            base_delay: 基础退避间隔（秒）

        Returns:
            退避间隔（秒），上限 1 小时
        """
        delay = base_delay * (2 ** retry_count)
        return min(delay, RecoveryManager.MAX_BACKOFF)
