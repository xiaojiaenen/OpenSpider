"""BaseSink — 所有 Sink 的基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSink(ABC):
    """数据输出基类

    子类实现 write() 方法，将爬取数据写入目标存储。
    """

    def __init__(self, config: dict):
        self.config = config
        self.spider_name = config.get("spider_name", "")
        self.user_id = config.get("user_id", "")
        self._buffer: list[dict] = []
        self._batch_size = config.get("batch_size", 100)

    @abstractmethod
    async def open(self):
        """初始化连接/文件"""
        pass

    @abstractmethod
    async def close(self):
        """关闭连接/刷新缓冲区"""
        pass

    @abstractmethod
    async def _write_batch(self, items: list[dict]):
        """批量写入子类实现"""
        pass

    async def write(self, item: dict):
        """写入单条数据，缓冲满时批量写入"""
        self._buffer.append(item)
        if len(self._buffer) >= self._batch_size:
            await self.flush()

    async def flush(self):
        """刷新缓冲区"""
        if self._buffer:
            await self._write_batch(self._buffer)
            self._buffer.clear()

    def _table_name(self) -> str:
        """生成表名（带用户前缀）"""
        prefix = f"u{self.user_id.replace('-', '')[:16]}_" if self.user_id else ""
        return f"{prefix}{self.spider_name}"
