"""API 路由 — 爬虫管理、任务查询、数据导出"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Depends
from openspider.api.auth import get_current_user
from openspider.api.user_context import UserContext, get_ctx
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
    SpiderVisibilityRequest,
    SpiderDataResponse,
    SpiderFieldsResponse,
    TaskInfo,
    TaskListResponse,
    LogInfo,
    LogListResponse,
)
from openspider.core.data_manager import SpiderDataManager
from openspider.models.spider import SpiderModel, SpiderStatus
from openspider.models.task import TaskModel
from openspider.models.log import LogModel
from openspider.storage.database import async_session

router = APIRouter(dependencies=[Depends(get_current_user)])

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


async def _get_spider_from_db(spider_id: int) -> SpiderModel:
    """通过 id 从数据库查询爬虫"""
    async with async_session() as session:
        result = await session.execute(
            select(SpiderModel).where(SpiderModel.id == spider_id)
        )
        db_spider = result.scalar_one_or_none()
    if db_spider is None:
        raise HTTPException(status_code=404, detail=f"爬虫 id={spider_id} 不存在")
    return db_spider




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
async def list_spiders(ctx: UserContext = Depends(get_ctx)):
    """列出爬虫（按用户隔离，包含公开爬虫）"""
    engine = get_engine()

    # 查询数据库获取 owner 和 is_public 信息
    async with async_session() as session:
        if ctx.is_admin:
            result = await session.execute(select(SpiderModel))
        else:
            # 非管理员可见：自己的爬虫 + 公开爬虫
            result = await session.execute(
                select(SpiderModel).where(
                    (SpiderModel.owner_user_id == ctx.user_id) |
                    (SpiderModel.is_public == True)
                )
            )
        db_spiders = {s.name: s for s in result.scalars().all()}

    spiders = []
    for info in engine.registry.list_all():
        db_info = db_spiders.get(info["name"])
        status_info = engine.get_spider_status(info["name"])
        spiders.append(SpiderInfo(
            id=db_info.id if db_info else None,
            name=info["name"],
            description=info.get("description", ""),
            schedule=info.get("schedule"),
            use_stealth=info.get("use_stealth", False),
            owner_user_id=db_info.owner_user_id if db_info else None,
            is_public=db_info.is_public if db_info else False,
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


@router.post("/spiders/{spider_id}/start", response_model=SpiderActionResponse)
async def start_spider(spider_id: int, body: SpiderStartRequest = SpiderStartRequest(),
                       ctx: UserContext = Depends(get_ctx)):
    """启动爬虫（允许 owner 或公开爬虫）"""
    engine = get_engine()
    db_spider = await _get_spider_from_db(spider_id)

    # 权限检查：owner 或公开爬虫
    is_owner = db_spider.owner_user_id == ctx.user_id
    if not is_owner and not db_spider.is_public and not ctx.is_admin:
        raise HTTPException(status_code=403, detail="无权启动该爬虫")

    name = db_spider.name
    try:
        task = await engine.start_spider(name, params=body.params, user_id=ctx.user_id)
        return SpiderActionResponse(
            success=True,
            message=f"爬虫 {name} 已启动",
            task_id=task.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/spiders/{spider_id}/stop", response_model=SpiderActionResponse)
async def stop_spider(spider_id: int, ctx: UserContext = Depends(get_ctx)):
    """停止爬虫（仅 owner）"""
    engine = get_engine()
    db_spider = await _get_spider_from_db(spider_id)

    is_owner = db_spider.owner_user_id == ctx.user_id
    if not is_owner and not ctx.is_admin:
        raise HTTPException(status_code=403, detail="无权操作该爬虫")

    name = db_spider.name
    stopped = await engine.stop_spider(name)
    if not stopped:
        raise HTTPException(status_code=400, detail=f"爬虫 {name} 未在运行")
    return SpiderActionResponse(success=True, message=f"爬虫 {name} 已停止")


@router.post("/spiders/{spider_id}/pause", response_model=SpiderActionResponse)
async def pause_spider(spider_id: int, ctx: UserContext = Depends(get_ctx)):
    """暂停爬虫（仅 owner，断点保留，可通过 resume 恢复）"""
    engine = get_engine()
    db_spider = await _get_spider_from_db(spider_id)

    is_owner = db_spider.owner_user_id == ctx.user_id
    if not is_owner and not ctx.is_admin:
        raise HTTPException(status_code=403, detail="无权操作该爬虫")

    name = db_spider.name
    paused = await engine.pause_spider(name)
    if not paused:
        raise HTTPException(status_code=400, detail=f"爬虫 {name} 未在运行")
    return SpiderActionResponse(success=True, message=f"爬虫 {name} 已暂停（断点已保存）")


@router.post("/spiders/{spider_id}/resume", response_model=SpiderActionResponse)
async def resume_spider(spider_id: int, ctx: UserContext = Depends(get_ctx)):
    """从断点恢复爬虫（仅 owner，恢复上一次暂停时的进度）"""
    engine = get_engine()
    db_spider = await _get_spider_from_db(spider_id)

    is_owner = db_spider.owner_user_id == ctx.user_id
    if not is_owner and not ctx.is_admin:
        raise HTTPException(status_code=403, detail="无权操作该爬虫")

    name = db_spider.name
    try:
        task = await engine.resume_spider(name, user_id=ctx.user_id)
        return SpiderActionResponse(
            success=True,
            message=f"爬虫 {name} 已从断点恢复",
            task_id=task.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/spiders/{spider_id}", response_model=SpiderActionResponse)
async def delete_spider(spider_id: int, ctx: UserContext = Depends(get_ctx)):
    """删除爬虫（仅 owner，先停止）"""
    engine = get_engine()
    db_spider = await _get_spider_from_db(spider_id)

    is_owner = db_spider.owner_user_id == ctx.user_id
    if not is_owner and not ctx.is_admin:
        raise HTTPException(status_code=403, detail="无权删除该爬虫")

    name = db_spider.name
    if name in engine._runners and engine._runners[name].is_running:
        await engine.stop_spider(name)

    unregistered = engine.registry.unregister(name)
    if not unregistered:
        raise HTTPException(status_code=404, detail=f"爬虫 {name} 不存在")

    # 从数据库删除
    async with async_session() as session:
        await session.execute(
            update(SpiderModel).where(SpiderModel.id == spider_id).values(status=SpiderStatus.DISABLED)
        )
        await session.commit()

    return SpiderActionResponse(success=True, message=f"爬虫 {name} 已删除")


@router.put("/spiders/{spider_id}/visibility", response_model=SpiderActionResponse)
async def set_spider_visibility(
    spider_id: int, body: SpiderVisibilityRequest, ctx: UserContext = Depends(get_ctx)
):
    """切换爬虫公开/私有（仅 owner）"""
    db_spider = await _get_spider_from_db(spider_id)

    is_owner = db_spider.owner_user_id == ctx.user_id
    if not is_owner and not ctx.is_admin:
        raise HTTPException(status_code=403, detail="无权修改该爬虫的可见性")

    async with async_session() as session:
        await session.execute(
            update(SpiderModel)
            .where(SpiderModel.id == spider_id)
            .values(is_public=body.is_public)
        )
        await session.commit()

    visibility = "公开" if body.is_public else "私有"
    return SpiderActionResponse(success=True, message=f"爬虫 {db_spider.name} 已设为{visibility}")


@router.post("/spiders/upload", response_model=SpiderUploadResponse)
async def upload_spider(file: UploadFile = File(...),
                        ctx: UserContext = Depends(get_ctx)):
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
    ctx: UserContext = Depends(get_ctx),
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


# === 数据查询（按爬虫隔离） ===

async def _build_data_manager(spider_id: int) -> SpiderDataManager:
    """异步构建 SpiderDataManager"""
    engine = get_engine()

    async with async_session() as session:
        result = await session.execute(
            select(SpiderModel).where(SpiderModel.id == spider_id)
        )
        db_spider = result.scalar_one_or_none()

    if db_spider is None:
        raise HTTPException(status_code=404, detail=f"爬虫 id={spider_id} 不存在")

    # 从 engine.registry 获取爬虫类的 fields 定义
    spider_cls = engine.registry.get(db_spider.name)
    fields = getattr(spider_cls, "fields", []) if spider_cls else []
    dedup_key = getattr(spider_cls, "dedup_key", None) if spider_cls else None

    return SpiderDataManager(
        db_session_factory=async_session,
        spider_id=spider_id,
        spider_name=db_spider.name,
        fields=fields,
        dedup_key=dedup_key,
    )


@router.get("/spiders/{spider_id}/data", response_model=SpiderDataResponse)
async def get_spider_data(
    spider_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: str | None = Query(None, description="按用户筛选（管理员可用）"),
    ctx: UserContext = Depends(get_ctx),
):
    """查询爬虫数据（按爬虫隔离，每张表独立）"""
    # 权限检查
    async with async_session() as session:
        result = await session.execute(
            select(SpiderModel).where(SpiderModel.id == spider_id)
        )
        db_spider = result.scalar_one_or_none()

    if db_spider is None:
        raise HTTPException(status_code=404, detail=f"爬虫 id={spider_id} 不存在")

    # 非管理员只能看自己的或公开爬虫的数据
    if not ctx.is_admin and ctx.user_id:
        is_owner = db_spider.owner_user_id == ctx.user_id
        if not is_owner and not db_spider.is_public:
            raise HTTPException(status_code=403, detail="无权查看该爬虫数据")

    dm = await _build_data_manager(spider_id)

    # 确保表存在
    await dm.ensure_table()

    # 非管理员只能查自己的数据
    query_user_id = user_id if ctx.is_admin else ctx.user_id

    result = await dm.query(
        user_id=query_user_id,
        page=page,
        page_size=page_size,
    )

    return SpiderDataResponse(
        items=result["items"],
        total=result["total"],
        page=page,
        page_size=page_size,
        columns=dm.get_field_names(),
    )


@router.get("/spiders/{spider_id}/export")
async def export_spider_data(
    spider_id: int,
    format: str = Query("json", description="导出格式: json/jsonl/csv"),
    limit: int = Query(10000, ge=1, le=100000),
    user_id: str | None = Query(None, description="按用户筛选（管理员可用）"),
    ctx: UserContext = Depends(get_ctx),
):
    """导出爬虫数据"""
    # 权限检查
    async with async_session() as session:
        result = await session.execute(
            select(SpiderModel).where(SpiderModel.id == spider_id)
        )
        db_spider = result.scalar_one_or_none()

    if db_spider is None:
        raise HTTPException(status_code=404, detail=f"爬虫 id={spider_id} 不存在")

    if not ctx.is_admin and ctx.user_id:
        is_owner = db_spider.owner_user_id == ctx.user_id
        if not is_owner and not db_spider.is_public:
            raise HTTPException(status_code=403, detail="无权导出该爬虫数据")

    dm = await _build_data_manager(spider_id)
    await dm.ensure_table()

    query_user_id = user_id if ctx.is_admin else ctx.user_id
    items = await dm.export(user_id=query_user_id, limit=limit)

    if format == "json":
        import json
        return {"data": items, "count": len(items)}

    elif format == "jsonl":
        import json
        lines = [json.dumps(item, ensure_ascii=False) for item in items]
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines), media_type="application/x-ndjson")

    elif format == "csv":
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        if items:
            writer = csv.DictWriter(output, fieldnames=items[0].keys())
            writer.writeheader()
            for item in items:
                writer.writerow(item)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={db_spider.name}.csv"},
        )

    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")


@router.get("/spiders/{spider_id}/fields", response_model=SpiderFieldsResponse)
async def get_spider_fields(spider_id: int):
    """获取爬虫的字段定义"""
    dm = await _build_data_manager(spider_id)
    return SpiderFieldsResponse(
        spider_id=spider_id,
        spider_name=dm.spider_name,
        fields=dm.fields,
        dedup_key=dm.dedup_key,
    )


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
                "follow(url, response=None, callback=None)",
                "request(url, callback=None)",
                "fetch(url, **kwargs) -> Response",
                "select(response, selector, css=True) -> 自适应选择器",
                "export_items(items, format, path) -> 导出工具",
                "concurrent_fetch(urls, max_concurrent, callback)",
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
        "scrapling_integration": {
            "version": ">=0.4.8",
            "features_used": [
                "FetcherSession — TLS 指纹伪装 HTTP 请求",
                "AsyncStealthySession — 隐身浏览器反爬绕过",
                "Spider 框架 — 并发调度/请求去重/暂停恢复",
                "CrawlSpider — 规则驱动自动链接跟进",
                "SitemapSpider — Sitemap 驱动爬取",
                "ProxyRotator — 多代理自动轮换",
                "capture_xhr — XHR/Fetch API 拦截",
                "page_action/page_setup — 浏览器页面交互",
                "development_mode — 响应缓存（开发调试）",
                "adaptive — 自适应选择器（页面结构变化后自动重定位）",
                "crawldir — 断点保存/恢复",
                "result.items + result.stats — 结果导出与统计",
            ],
        },
        "api_docs": "/docs",
        "supported_export_formats": ["json", "jsonl", "csv", "parquet"],
        "api_extra": {
            "resume": "POST /spiders/{name}/resume — 从断点恢复",
        },
    }


# === 管理员接口 ===

@router.get("/admin/users")
async def list_users(ctx: UserContext = Depends(get_ctx)):
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
async def list_user_spiders(user_id: str, ctx: UserContext = Depends(get_ctx)):
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
async def admin_stats(ctx: UserContext = Depends(get_ctx)):
    """全局统计（管理员）"""
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    async with async_session() as session:
        spider_count = (await session.execute(select(func.count()).select_from(SpiderModel))).scalar()
        task_count = (await session.execute(select(func.count()).select_from(TaskModel))).scalar()
    return {"spiders": spider_count, "tasks": task_count}
