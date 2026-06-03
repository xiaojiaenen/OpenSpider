"""任务调度器 — 基于 APScheduler 的定时任务管理"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class SpiderScheduler:
    """任务调度器

    职责：
    - 读取爬虫的 schedule 字段（cron 表达式），自动注册定时触发
    - 支持手动触发立即启动
    - 单例保护：同一爬虫同一时间只能有一个实例在运行
    - 爬虫重新注册时自动更新调度计划
    """

    def __init__(self, engine):
        self.engine = engine
        self._scheduler = AsyncIOScheduler()
        self._job_map: dict[str, str] = {}  # spider_name -> job_id

    def start(self) -> None:
        """启动调度器"""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("任务调度器已启动")

    def shutdown(self) -> None:
        """关闭调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("任务调度器已关闭")

    async def sync_schedules(self) -> None:
        """同步所有爬虫的调度计划"""
        for name, cls in self.engine.registry.spiders.items():
            schedule = getattr(cls, "schedule", None)
            if schedule:
                self.add_schedule(name, schedule)

    def add_schedule(self, spider_name: str, cron_expression: str) -> None:
        """添加或更新爬虫的定时调度

        Args:
            spider_name: 爬虫名称
            cron_expression: cron 表达式，格式如 "0 */6 * * *"（每6小时）
        """
        # 移除旧任务
        self.remove_schedule(spider_name)

        try:
            trigger = CronTrigger.from_crontab(cron_expression)
            job = self._scheduler.add_job(
                self._trigger_spider,
                trigger=trigger,
                args=[spider_name],
                id=f"spider_{spider_name}",
                name=f"定时爬虫: {spider_name}",
                replace_existing=True,
            )
            self._job_map[spider_name] = job.id
            logger.info(f"添加定时调度: {spider_name} -> {cron_expression}")
        except Exception as e:
            logger.error(f"添加调度失败: {spider_name}: {e}")

    def remove_schedule(self, spider_name: str) -> bool:
        """移除爬虫的定时调度"""
        job_id = self._job_map.pop(spider_name, None)
        if job_id:
            try:
                self._scheduler.remove_job(job_id)
                logger.info(f"移除定时调度: {spider_name}")
                return True
            except Exception:
                pass
        return False

    def get_schedules(self) -> list[dict]:
        """获取所有调度任务"""
        result = []
        for job in self._scheduler.get_jobs():
            spider_name = job.args[0] if job.args else "unknown"
            result.append({
                "spider_name": spider_name,
                "job_id": job.id,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return result

    async def _trigger_spider(self, spider_name: str) -> None:
        """调度触发回调"""
        # 检查是否已在运行
        runner = self.engine._runners.get(spider_name)
        if runner and runner.is_running:
            logger.info(f"爬虫 {spider_name} 已在运行，跳过本次调度")
            return

        try:
            await self.engine.start_spider(spider_name)
            logger.info(f"调度触发爬虫: {spider_name}")
        except Exception as e:
            logger.error(f"调度触发失败: {spider_name}: {e}")
