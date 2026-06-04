"""调度任务模型 — 动态定时任务"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from openspider.storage.database import Base


class ScheduleStatus(str, enum.Enum):
    """调度状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"


class ScheduleModel(Base):
    """调度任务表"""
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spider_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cron: Mapped[str] = mapped_column(String(64), nullable=False)  # cron 表达式
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus), default=ScheduleStatus.ENABLED, nullable=False
    )
    next_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
