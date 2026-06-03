"""爬虫注册信息模型"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from openspider.storage.database import Base


class SpiderStatus(str, enum.Enum):
    """爬虫状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    DISABLED = "disabled"


class SpiderModel(Base):
    """爬虫注册信息表"""
    __tablename__ = "spiders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    schedule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    retry_delay: Mapped[int] = mapped_column(Integer, default=60)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[SpiderStatus] = mapped_column(
        Enum(SpiderStatus), default=SpiderStatus.IDLE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
