"""爬取数据项模型"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from openspider.storage.database import Base


class ItemModel(Base):
    """爬取数据表"""
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    spider_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), default="")
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
