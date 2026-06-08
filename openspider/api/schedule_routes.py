"""调度任务 API 路由"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update, delete

from openspider.api.auth import get_current_user
from openspider.api.user_context import UserContext, get_ctx
from openspider.models.user import UserModel
from openspider.models.schedule import ScheduleModel, ScheduleStatus
from openspider.storage.database import async_session

schedule_router = APIRouter(prefix="/schedules", tags=["schedules"], dependencies=[Depends(get_current_user)])


# === 请求/响应模型 ===

class ScheduleCreate(BaseModel):
    spider_name: str
    cron: str
    params: dict = {}


class ScheduleUpdate(BaseModel):
    cron: str | None = None
    params: dict | None = None


class ScheduleInfo(BaseModel):
    id: int
    spider_name: str
    cron: str
    params: dict | None = None
    owner_user_id: str | None = None
    status: str
    next_run: datetime | None = None
    last_run: datetime | None = None
    last_status: str | None = None
    run_count: int = 0


class ScheduleListResponse(BaseModel):
    schedules: list[ScheduleInfo]
    total: int


# === 路由 ===

@schedule_router.get("", response_model=ScheduleListResponse)
async def list_schedules(ctx: UserContext = Depends(get_ctx)):
    """列出所有调度"""
    async with async_session() as session:
        query = select(ScheduleModel).order_by(ScheduleModel.created_at.desc())
        if not ctx.is_admin and ctx.user_id:
            query = query.where(
                (ScheduleModel.owner_user_id == ctx.user_id) |
                (ScheduleModel.owner_user_id.is_(None))
            )
        result = await session.execute(query)
        schedules = result.scalars().all()

    return ScheduleListResponse(
        schedules=[
            ScheduleInfo(
                id=s.id, spider_name=s.spider_name, cron=s.cron,
                params=s.params, owner_user_id=s.owner_user_id,
                status=s.status.value, next_run=s.next_run,
                last_run=s.last_run, last_status=s.last_status,
                run_count=s.run_count,
            )
            for s in schedules
        ],
        total=len(schedules),
    )


@schedule_router.post("", response_model=ScheduleInfo)
async def create_schedule(body: ScheduleCreate, ctx: UserContext = Depends(get_ctx)):
    """创建调度"""
    from openspider.api.routes import get_engine
    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="引擎未初始化")

    # 校验爬虫存在
    spider_cls = engine.registry.get(body.spider_name)
    if spider_cls is None:
        raise HTTPException(status_code=404, detail=f"爬虫 {body.spider_name} 不存在")

    # 计算下次运行时间
    next_run = _calculate_next_run(body.cron)

    async with async_session() as session:
        schedule = ScheduleModel(
            spider_name=body.spider_name,
            cron=body.cron,
            params=body.params,
            owner_user_id=ctx.user_id,
            status=ScheduleStatus.ENABLED,
            next_run=next_run,
        )
        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)

    # 注册到调度器
    if engine.scheduler:
        engine.scheduler.add_schedule(body.spider_name, body.cron, schedule_id=schedule.id)

    return ScheduleInfo(
        id=schedule.id, spider_name=schedule.spider_name,
        cron=schedule.cron, params=schedule.params,
        owner_user_id=schedule.owner_user_id,
        status=schedule.status.value, next_run=schedule.next_run,
    )


@schedule_router.get("/{schedule_id}", response_model=ScheduleInfo)
async def get_schedule(schedule_id: int, ctx: UserContext = Depends(get_ctx)):
    """获取调度详情"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(status_code=404, detail="调度不存在")

    return ScheduleInfo(
        id=schedule.id, spider_name=schedule.spider_name,
        cron=schedule.cron, params=schedule.params,
        owner_user_id=schedule.owner_user_id,
        status=schedule.status.value, next_run=schedule.next_run,
        last_run=schedule.last_run, last_status=schedule.last_status,
        run_count=schedule.run_count,
    )


@schedule_router.put("/{schedule_id}", response_model=ScheduleInfo)
async def update_schedule(schedule_id: int, body: ScheduleUpdate,
                          ctx: UserContext = Depends(get_ctx)):
    """修改调度"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(status_code=404, detail="调度不存在")

        if body.cron is not None:
            schedule.cron = body.cron
            schedule.next_run = _calculate_next_run(body.cron)
        if body.params is not None:
            schedule.params = body.params
        await session.commit()
        await session.refresh(schedule)

    # 更新调度器
    from openspider.api.routes import get_engine
    _engine = get_engine()
    if _engine and _engine.scheduler:
        _engine.scheduler.add_schedule(schedule.spider_name, schedule.cron, schedule_id=schedule.id)

    return ScheduleInfo(
        id=schedule.id, spider_name=schedule.spider_name,
        cron=schedule.cron, params=schedule.params,
        owner_user_id=schedule.owner_user_id,
        status=schedule.status.value, next_run=schedule.next_run,
        last_run=schedule.last_run, last_status=schedule.last_status,
        run_count=schedule.run_count,
    )


@schedule_router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: int, ctx: UserContext = Depends(get_ctx)):
    """删除调度"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(status_code=404, detail="调度不存在")

        spider_name = schedule.spider_name
        await session.delete(schedule)
        await session.commit()

    # 从调度器移除
    from openspider.api.routes import get_engine
    _engine = get_engine()
    if _engine and _engine.scheduler:
        _engine.scheduler.remove_schedule(spider_name)

    return {"success": True, "message": "调度已删除"}


@schedule_router.post("/{schedule_id}/enable")
async def enable_schedule(schedule_id: int, ctx: UserContext = Depends(get_ctx)):
    """启用调度"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(status_code=404, detail="调度不存在")

        schedule.status = ScheduleStatus.ENABLED
        schedule.next_run = _calculate_next_run(schedule.cron)
        await session.commit()

    from openspider.api.routes import get_engine
    _engine = get_engine()
    if _engine and _engine.scheduler:
        _engine.scheduler.add_schedule(schedule.spider_name, schedule.cron, schedule_id=schedule.id)

    return {"success": True, "message": "调度已启用"}


@schedule_router.post("/{schedule_id}/disable")
async def disable_schedule(schedule_id: int, ctx: UserContext = Depends(get_ctx)):
    """禁用调度"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(status_code=404, detail="调度不存在")

        schedule.status = ScheduleStatus.DISABLED
        schedule.next_run = None
        await session.commit()

    from openspider.api.routes import get_engine
    _engine = get_engine()
    if _engine and _engine.scheduler:
        _engine.scheduler.remove_schedule(schedule.spider_name)

    return {"success": True, "message": "调度已禁用"}


@schedule_router.get("/{schedule_id}/runs")
async def schedule_runs(schedule_id: int, limit: int = Query(20, ge=1, le=100),
                        ctx: UserContext = Depends(get_ctx)):
    """查看调度执行历史"""
    async with async_session() as session:
        result = await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(status_code=404, detail="调度不存在")

        from openspider.models.task import TaskModel
        query = (
            select(TaskModel)
            .where(TaskModel.spider_name == schedule.spider_name)
            .order_by(TaskModel.created_at.desc())
            .limit(limit)
        )
        if not ctx.is_admin and ctx.user_id:
            query = query.where(
                (TaskModel.owner_user_id == ctx.user_id) |
                (TaskModel.owner_user_id.is_(None))
            )
        tasks_result = await session.execute(query)
        tasks = tasks_result.scalars().all()

    return {
        "schedule_id": schedule_id,
        "spider_name": schedule.spider_name,
        "runs": [
            {
                "task_id": t.id,
                "status": t.status.value if hasattr(t.status, 'value') else t.status,
                "started_at": str(t.started_at) if t.started_at else None,
                "finished_at": str(t.finished_at) if t.finished_at else None,
                "items_scraped": t.items_scraped,
            }
            for t in tasks
        ],
    }


def _calculate_next_run(cron_expr: str) -> datetime | None:
    """从 cron 表达式计算下次运行时间"""
    try:
        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger.from_crontab(cron_expr)
        return trigger.get_next_fire_time(None, datetime.now())
    except Exception:
        return None
