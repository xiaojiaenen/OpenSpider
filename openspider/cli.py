"""CLI 入口"""

from __future__ import annotations

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="OpenSpider")
def main():
    """OpenSpider — 爬虫管理平台"""
    pass


@main.command()
@click.option("--host", default=None, help="API 服务地址")
@click.option("--port", default=None, type=int, help="API 服务端口")
def serve(host, port):
    """启动平台（API 服务 + 调度器 + 文件监控）"""
    from openspider.main import serve as start_serve
    start_serve(host=host, port=port)


@main.command()
def list():
    """列出所有爬虫"""
    import asyncio
    asyncio.run(_list_spiders())


async def _list_spiders():
    from openspider.core.registry import SpiderRegistry
    from openspider.config import settings

    registry = SpiderRegistry(settings.spiders_dir)
    count = registry.scan_directory()
    click.echo(f"扫描到 {count} 个爬虫:\n")
    for info in registry.list_all():
        click.echo(f"  {info['name']:20s} | {info.get('description', '')[:40]}")


@main.command()
@click.argument("name")
def start(name):
    """启动指定爬虫"""
    import asyncio
    asyncio.run(_start_spider(name))


async def _start_spider(name: str):
    from openspider.core.engine import Engine
    from openspider.storage.database import init_db

    await init_db()
    engine = Engine()
    engine.registry.scan_directory()
    try:
        task = await engine.start_spider(name)
        click.echo(f"爬虫 {name} 已启动，任务ID: {task.id}")
        # 等待爬虫完成
        if name in engine._runners:
            await engine._runners[name]._task
    except ValueError as e:
        click.echo(f"错误: {e}", err=True)
    finally:
        await engine.shutdown()


@main.command()
@click.argument("name")
def stop(name):
    """停止指定爬虫"""
    import asyncio
    asyncio.run(_stop_spider(name))


async def _stop_spider(name: str):
    from openspider.core.engine import Engine
    from openspider.storage.database import init_db

    await init_db()
    engine = Engine()
    stopped = await engine.stop_spider(name)
    if stopped:
        click.echo(f"爬虫 {name} 已停止")
    else:
        click.echo(f"爬虫 {name} 未在运行")
    await engine.shutdown()


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
def validate(file_path):
    """验证爬虫文件是否合法"""
    from pathlib import Path
    from openspider.core.registry import SpiderRegistry
    from openspider.config import settings

    registry = SpiderRegistry(settings.spiders_dir)
    try:
        registry.register_file(Path(file_path))
        click.echo("✓ 爬虫文件校验通过")
    except ValueError as e:
        click.echo(f"✗ 校验失败: {e}", err=True)


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
def add(file_path):
    """上传注册新爬虫"""
    import shutil
    from pathlib import Path
    from openspider.core.registry import SpiderRegistry
    from openspider.config import settings

    src = Path(file_path)
    dst = settings.spiders_dir / src.name
    shutil.copy2(src, dst)

    registry = SpiderRegistry(settings.spiders_dir)
    try:
        registry.register_file(dst)
        click.echo(f"✓ 爬虫已注册: {src.name}")
    except ValueError as e:
        dst.unlink(missing_ok=True)
        click.echo(f"✗ 注册失败: {e}", err=True)


@main.command()
@click.argument("name")
def info(name):
    """查看爬虫详情"""
    import asyncio
    asyncio.run(_show_info(name))


async def _show_info(name: str):
    from openspider.core.registry import SpiderRegistry
    from openspider.config import settings

    registry = SpiderRegistry(settings.spiders_dir)
    registry.scan_directory()

    cls = registry.get(name)
    if cls is None:
        click.echo(f"爬虫 {name} 不存在")
        return

    click.echo(f"名称:       {cls.name}")
    click.echo(f"描述:       {getattr(cls, 'description', '')}")
    click.echo(f"调度:       {getattr(cls, 'schedule', None) or '手动'}")
    click.echo(f"隐身模式:   {getattr(cls, 'use_stealth', False)}")
    click.echo(f"重试次数:   {getattr(cls, 'max_retries', 3)}")
    click.echo(f"重试间隔:   {getattr(cls, 'retry_delay', 60)}s")
    click.echo(f"并发数:     {getattr(cls, 'concurrent_requests', 4)}")
    click.echo(f"请求间隔:   {getattr(cls, 'download_delay', 0.5)}s")


@main.command()
@click.option("--spider", default=None, help="按爬虫筛选")
@click.option("--status", default=None, help="按状态筛选")
@click.option("--limit", default=20, help="显示条数")
def tasks(spider, status, limit):
    """查看任务列表"""
    import asyncio
    asyncio.run(_list_tasks(spider, status, limit))


async def _list_tasks(spider, status, limit):
    from openspider.storage.database import init_db, async_session
    from openspider.models.task import TaskModel
    from sqlalchemy import select

    await init_db()
    async with async_session() as session:
        query = select(TaskModel).order_by(TaskModel.created_at.desc())
        if spider:
            query = query.where(TaskModel.spider_name == spider)
        if status:
            query = query.where(TaskModel.status == status)
        query = query.limit(limit)
        result = await session.execute(query)
        task_list = result.scalars().all()

    if not task_list:
        click.echo("暂无任务")
        return

    click.echo(f"{'ID':<8} {'爬虫':<15} {'状态':<12} {'数据':<8} {'错误':<6} {'时间'}")
    click.echo("-" * 70)
    for t in task_list:
        status_val = t.status.value if hasattr(t.status, 'value') else t.status
        click.echo(f"{t.id:<8} {t.spider_name:<15} {status_val:<12} {t.items_scraped:<8} {t.errors_count:<6} {str(t.created_at)[:19]}")


@main.command()
@click.argument("task_id", type=int)
def logs(task_id):
    """查看任务日志"""
    import asyncio
    asyncio.run(_show_logs(task_id))


async def _show_logs(task_id):
    from openspider.storage.database import init_db, async_session
    from openspider.models.log import LogModel
    from sqlalchemy import select

    await init_db()
    async with async_session() as session:
        result = await session.execute(
            select(LogModel)
            .where(LogModel.task_id == task_id)
            .order_by(LogModel.created_at.desc())
            .limit(100)
        )
        log_list = result.scalars().all()

    if not log_list:
        click.echo(f"任务 {task_id} 暂无日志")
        return

    for log in log_list:
        level_val = log.level.value if hasattr(log.level, 'value') else log.level
        click.echo(f"[{str(log.created_at)[:19]}] [{level_val.upper():8}] {log.message}")


@main.command()
@click.argument("name")
@click.option("--format", "fmt", default="json", help="导出格式: json/jsonl/csv")
@click.option("--limit", default=10000, help="最大条数")
def export(name, fmt, limit):
    """导出爬取数据"""
    import asyncio
    asyncio.run(_export_data(name, fmt, limit))


async def _export_data(name, fmt, limit):
    import json
    from openspider.storage.database import init_db, async_session
    from openspider.models.item import ItemModel
    from sqlalchemy import select

    await init_db()
    async with async_session() as session:
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.spider_name == name)
            .order_by(ItemModel.crawled_at.desc())
            .limit(limit)
        )
        items = result.scalars().all()

    if not items:
        click.echo(f"爬虫 {name} 暂无数据")
        return

    if fmt == "json":
        data = [i.data for i in items]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    elif fmt == "jsonl":
        for i in items:
            click.echo(json.dumps(i.data, ensure_ascii=False))
    elif fmt == "csv":
        import csv
        import sys
        if items:
            writer = csv.DictWriter(sys.stdout, fieldnames=items[0].data.keys())
            writer.writeheader()
            for i in items:
                writer.writerow(i.data)
    else:
        click.echo(f"不支持的格式: {fmt}", err=True)

    click.echo(f"\n# 共 {len(items)} 条", err=True)


if __name__ == "__main__":
    main()
