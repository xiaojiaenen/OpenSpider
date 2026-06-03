"""API 路由 — 爬虫管理、任务查询、数据导出"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Depends
from openspider.api.auth import verify_api_key
from openspider.api.user_context import UserContext, get_user_context
from sqlalchemy import select, func, update

from openspider import __version__
from openspider.config import settings
from openspider.api.schemas import (
    HealthResponse,
    SpiderInfo,
    SpiderListResponse,
    SpiderStartRequest,
    SpiderActionResponse,
    SpiderUploadResponse,
    TaskInfo,
    TaskListResponse,
    ItemInfo,
    ItemListResponse,
    LogInfo,
    LogListResponse,
)
from openspider.models.spider import SpiderModel, SpiderStatus
from openspider.models.task import TaskModel, TaskStatus
from openspider.models.item import ItemModel
from openspider.models.log import LogModel
from openspider.storage.database import async_session

router = APIRouter(dependencies=[Depends(verify_api_key)])

# 不需要认证的路由单独创建
public_router = APIRouter()

# 全局引擎实例（由 main.py 注入）
_engine = None


def set_engine(engine):
    """设置全局引擎实例"""
    global _engine
    _engine = engine


def get_engine():
    """获取全局引擎实例"""
    if _engine is None:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    return _engine


# === 健康检查（不需要认证） ===

@public_router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    engine = get_engine()
    mysql_ok = False
    try:
        async with async_session() as session:
            await session.execute(select(func.count()).select_from(SpiderModel))
            mysql_ok = True
    except Exception:
        pass

    active = sum(1 for r in engine._runners.values() if r.is_running)

    return HealthResponse(
        status="ok",
        version=__version__,
        mysql_connected=mysql_ok,
        active_spiders=active,
        registered_spiders=len(engine.registry.spiders),
    )


# === 爬虫管理 ===

@router.get("/spiders", response_model=SpiderListResponse)
async def list_spiders(ctx: UserContext = Depends(get_user_context)):
    """列出爬虫（按用户隔离）"""
    engine = get_engine()

    # 查询数据库获取 owner 信息
    async with async_session() as session:
        if ctx.is_admin:
            result = await session.execute(select(SpiderModel))
        else:
            result = await session.execute(
                select(SpiderModel).where(
                    (SpiderModel.owner_user_id == ctx.user_id) |
                    (SpiderModel.owner_user_id.is_(None))
                )
            )
        db_spiders = {s.name: s for s in result.scalars().all()}

    spiders = []
    for info in engine.registry.list_all():
        db_info = db_spiders.get(info["name"])
        # 非管理员只看自己的或共享的
        if not ctx.is_admin and db_info and db_info.owner_user_id and db_info.owner_user_id != ctx.user_id:
            continue
        status_info = engine.get_spider_status(info["name"])
        spiders.append(SpiderInfo(
            name=info["name"],
            description=info.get("description", ""),
            schedule=info.get("schedule"),
            use_stealth=info.get("use_stealth", False),
            owner_user_id=db_info.owner_user_id if db_info else None,
            is_running=status_info["is_running"] if status_info else False,
            items_scraped=status_info["items_scraped"] if status_info else 0,
            requests_made=status_info["requests_made"] if status_info else 0,
            errors_count=status_info["errors_count"] if status_info else 0,
        ))
    return SpiderListResponse(spiders=spiders, total=len(spiders))


@router.get("/spiders/{name}", response_model=SpiderInfo)
async def get_spider(name: str):
    """获取单个爬虫详情"""
    engine = get_engine()
    spider_cls = engine.registry.get(name)
    if spider_cls is None:
        raise HTTPException(status_code=404, detail=f"爬虫 {name} 不存在")

    status_info = engine.get_spider_status(name)
    return SpiderInfo(
        name=name,
        description=getattr(spider_cls, "description", ""),
        schedule=getattr(spider_cls, "schedule", None),
        use_stealth=getattr(spider_cls, "use_stealth", False),
        is_running=status_info["is_running"] if status_info else False,
        items_scraped=status_info["items_scraped"] if status_info else 0,
        requests_made=status_info["requests_made"] if status_info else 0,
        errors_count=status_info["errors_count"] if status_info else 0,
    )


@router.post("/spiders/{name}/start", response_model=SpiderActionResponse)
async def start_spider(name: str, body: SpiderStartRequest = SpiderStartRequest(),
                       ctx: UserContext = Depends(get_user_context)):
    """启动爬虫"""
    engine = get_engine()
    try:
        task = await engine.start_spider(name, params=body.params, user_id=ctx.user_id)
        return SpiderActionResponse(
            success=True,
            message=f"爬虫 {name} 已启动",
            task_id=task.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/spiders/{name}/stop", response_model=SpiderActionResponse)
async def stop_spider(name: str):
    """停止爬虫"""
    engine = get_engine()
    stopped = await engine.stop_spider(name)
    if not stopped:
        raise HTTPException(status_code=400, detail=f"爬虫 {name} 未在运行")
    return SpiderActionResponse(success=True, message=f"爬虫 {name} 已停止")


@router.post("/spiders/{name}/pause", response_model=SpiderActionResponse)
async def pause_spider(name: str):
    """暂停爬虫"""
    engine = get_engine()
    paused = await engine.pause_spider(name)
    if not paused:
        raise HTTPException(status_code=400, detail=f"爬虫 {name} 未在运行")
    return SpiderActionResponse(success=True, message=f"爬虫 {name} 已暂停")


@router.delete("/spiders/{name}", response_model=SpiderActionResponse)
async def delete_spider(name: str):
    """删除爬虫（先停止）"""
    engine = get_engine()
    if name in engine._runners and engine._runners[name].is_running:
        await engine.stop_spider(name)

    unregistered = engine.registry.unregister(name)
    if not unregistered:
        raise HTTPException(status_code=404, detail=f"爬虫 {name} 不存在")

    # 从数据库删除
    async with async_session() as session:
        await session.execute(
            update(SpiderModel).where(SpiderModel.name == name).values(status=SpiderStatus.DISABLED)
        )
        await session.commit()

    return SpiderActionResponse(success=True, message=f"爬虫 {name} 已删除")


@router.post("/spiders/upload", response_model=SpiderUploadResponse)
async def upload_spider(file: UploadFile = File(...),
                        ctx: UserContext = Depends(get_user_context)):
    """上传爬虫文件"""
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持 .py 文件")

    engine = get_engine()

    # 保存到 spiders 目录
    target_path = settings.spiders_dir / file.filename
    content = await file.read()
    target_path.write_bytes(content)

    # 注册
    try:
        engine.registry.register_file(target_path)
        registered = [name for name, cls in engine.registry.spiders.items()
                      if str(target_path) in engine.registry._file_map]

        # 设置 owner_user_id
        if ctx.user_id:
            async with async_session() as session:
                for spider_name in registered:
                    await session.execute(
                        update(SpiderModel)
                        .where(SpiderModel.name == spider_name)
                        .values(owner_user_id=ctx.user_id)
                    )
                await session.commit()

        return SpiderUploadResponse(
            success=True,
            message=f"上传成功，注册了 {len(registered)} 个爬虫",
            registered_spiders=registered,
        )
    except ValueError as e:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))


# === 任务查询 ===

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    spider: str | None = Query(None, description="按爬虫筛选"),
    status: str | None = Query(None, description="按状态筛选"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: UserContext = Depends(get_user_context),
):
    """任务列表（按用户隔离）"""
    async with async_session() as session:
        query = select(TaskModel).order_by(TaskModel.created_at.desc())
        count_query = select(func.count()).select_from(TaskModel)

        # 用户隔离
        if not ctx.is_admin and ctx.user_id:
            query = query.where(
                (TaskModel.owner_user_id == ctx.user_id) |
                (TaskModel.owner_user_id.is_(None))
            )
            count_query = count_query.where(
                (TaskModel.owner_user_id == ctx.user_id) |
                (TaskModel.owner_user_id.is_(None))
            )

        if spider:
            query = query.where(TaskModel.spider_name == spider)
            count_query = count_query.where(TaskModel.spider_name == spider)
        if status:
            query = query.where(TaskModel.status == status)
            count_query = count_query.where(TaskModel.status == status)

        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        tasks = result.scalars().all()
        total = (await session.execute(count_query)).scalar() or 0

    return TaskListResponse(
        tasks=[
            TaskInfo(
                id=t.id,
                spider_name=t.spider_name,
                status=t.status.value if hasattr(t.status, 'value') else t.status,
                started_at=t.started_at,
                finished_at=t.finished_at,
                items_scraped=t.items_scraped,
                requests_made=t.requests_made,
                errors_count=t.errors_count,
                error_message=t.error_message,
                params=t.params,
            )
            for t in tasks
        ],
        total=total,
    )


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: int):
    """任务详情"""
    async with async_session() as session:
        result = await session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    return TaskInfo(
        id=task.id,
        spider_name=task.spider_name,
        status=task.status.value if hasattr(task.status, 'value') else task.status,
        started_at=task.started_at,
        finished_at=task.finished_at,
        items_scraped=task.items_scraped,
        requests_made=task.requests_made,
        errors_count=task.errors_count,
        error_message=task.error_message,
        params=task.params,
    )


@router.get("/tasks/{task_id}/logs", response_model=LogListResponse)
async def get_task_logs(task_id: int, limit: int = Query(100, ge=1, le=500)):
    """任务日志"""
    async with async_session() as session:
        query = (
            select(LogModel)
            .where(LogModel.task_id == task_id)
            .order_by(LogModel.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        logs = result.scalars().all()

    return LogListResponse(
        logs=[
            LogInfo(
                id=l.id,
                spider_name=l.spider_name,
                task_id=l.task_id,
                level=l.level.value if hasattr(l.level, 'value') else l.level,
                message=l.message,
                created_at=l.created_at,
            )
            for l in logs
        ],
        total=len(logs),
    )


# === 数据查询 ===

@router.get("/items", response_model=ItemListResponse)
async def list_items(
    spider: str | None = Query(None, description="按爬虫筛选"),
    task_id: int | None = Query(None, description="按任务筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: UserContext = Depends(get_user_context),
):
    """爬取数据查询（按用户隔离）"""
    offset = (page - 1) * page_size

    async with async_session() as session:
        query = select(ItemModel).order_by(ItemModel.crawled_at.desc())
        count_query = select(func.count()).select_from(ItemModel)

        # 非管理员只能看自己的数据
        if not ctx.is_admin and ctx.user_id:
            # 通过 spider 的 owner 过滤
            owned_spiders = select(SpiderModel.name).where(
                (SpiderModel.owner_user_id == ctx.user_id) |
                (SpiderModel.owner_user_id.is_(None))
            )
            query = query.where(ItemModel.spider_name.in_(owned_spiders))
            count_query = count_query.where(ItemModel.spider_name.in_(owned_spiders))

        if spider:
            query = query.where(ItemModel.spider_name == spider)
            count_query = count_query.where(ItemModel.spider_name == spider)
        if task_id:
            query = query.where(ItemModel.task_id == task_id)
            count_query = count_query.where(ItemModel.task_id == task_id)

        query = query.offset(offset).limit(page_size)

        result = await session.execute(query)
        items = result.scalars().all()
        total = (await session.execute(count_query)).scalar() or 0

    return ItemListResponse(
        items=[
            ItemInfo(
                id=i.id,
                spider_name=i.spider_name,
                task_id=i.task_id,
                data=i.data,
                url=i.url,
                crawled_at=i.crawled_at,
            )
            for i in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export/{spider_name}")
async def export_data(
    spider_name: str,
    format: str = Query("json", description="导出格式: json/jsonl/csv"),
    limit: int = Query(10000, ge=1, le=100000),
):
    """导出爬取数据"""
    async with async_session() as session:
        query = (
            select(ItemModel)
            .where(ItemModel.spider_name == spider_name)
            .order_by(ItemModel.crawled_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        items = result.scalars().all()

    if format == "json":
        import json
        data = [i.data for i in items]
        return {"data": data, "count": len(data)}

    elif format == "jsonl":
        import json
        lines = [json.dumps(i.data, ensure_ascii=False) for i in items]
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines), media_type="application/x-ndjson")

    elif format == "csv":
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        if items:
            writer = csv.DictWriter(output, fieldnames=items[0].data.keys())
            writer.writeheader()
            for item in items:
                writer.writerow(item.data)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={spider_name}.csv"},
        )

    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")


# === 能力描述 ===

@router.get("/capabilities")
async def get_capabilities():
    """返回平台能力描述（给 AI 用）"""
    return {
        "platform": "OpenSpider",
        "version": __version__,
        "spider_interface": {
            "base_class": "openspider.spiders.base.BaseSpider",
            "required_attributes": ["name"],
            "optional_attributes": [
                "description", "schedule", "max_retries", "retry_delay",
                "concurrent_requests", "download_delay", "use_stealth", "proxies",
                "encoding", "ssl_verify", "follow_redirects", "timeout",
                "default_headers", "cookies",
                "impersonate", "http3", "stealthy_headers",
                "block_ads", "blocked_domains", "dns_over_https",
                "locale", "timezone_id",
                "solve_cloudflare", "block_webrtc", "hide_canvas", "allow_webgl",
                "real_chrome", "cdp_url", "user_data_dir", "init_script", "max_pages",
                "disable_resources", "network_idle", "load_dom",
                "wait_selector", "wait_selector_state", "wait",
                "page_action", "page_setup", "capture_xhr",
                "adaptive", "adaptive_storage",
            ],
            "required_methods": ["run() -> AsyncGenerator[dict, None]"],
            "optional_hooks": ["on_start", "on_error", "on_complete", "on_item_scraped"],
            "helper_methods": [
                "get(url, **kwargs) -> Response",
                "post(url, **kwargs) -> Response",
            ],
            "example_code": (
                "from openspider.spiders.base import BaseSpider\n\n"
                "class MySpider(BaseSpider):\n"
                "    name = 'my_spider'\n"
                "    start_urls = ['https://example.com']\n\n"
                "    async def run(self):\n"
                "        page = await self.get(self.start_urls[0])\n"
                "        for item in page.css('.article'):\n"
                "            yield {'title': item.css('h2::text').get('')}\n"
            ),
        },
        "api_docs": "/docs",
        "supported_export_formats": ["json", "jsonl", "csv"],
    }


# === 管理员接口 ===

@router.get("/admin/users")
async def list_users(ctx: UserContext = Depends(get_user_context)):
    """列出所有用户（管理员）"""
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    async with async_session() as session:
        result = await session.execute(
            select(SpiderModel.owner_user_id, func.count())
            .where(SpiderModel.owner_user_id.is_not(None))
            .group_by(SpiderModel.owner_user_id)
        )
        users = [{"user_id": row[0], "spider_count": row[1]} for row in result.all()]
    return {"users": users}


@router.get("/admin/users/{user_id}/spiders")
async def list_user_spiders(user_id: str, ctx: UserContext = Depends(get_user_context)):
    """查看某个用户的爬虫（管理员）"""
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    async with async_session() as session:
        result = await session.execute(
            select(SpiderModel).where(SpiderModel.owner_user_id == user_id)
        )
        spiders = result.scalars().all()
    return {"user_id": user_id, "spiders": [s.name for s in spiders]}


@router.get("/admin/stats")
async def admin_stats(ctx: UserContext = Depends(get_user_context)):
    """全局统计（管理员）"""
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    async with async_session() as session:
        spider_count = (await session.execute(select(func.count()).select_from(SpiderModel))).scalar()
        task_count = (await session.execute(select(func.count()).select_from(TaskModel))).scalar()
        item_count = (await session.execute(select(func.count()).select_from(ItemModel))).scalar()
    return {"spiders": spider_count, "tasks": task_count, "items": item_count}
