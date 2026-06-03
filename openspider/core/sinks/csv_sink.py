"""CSV Sink — 写入 CSV 文件"""

from __future__ import annotations

import csv
from pathlib import Path

from openspider.core.sinks.base import BaseSink


class CsvSink(BaseSink):
    """将爬取数据写入 CSV 文件"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.file_path = Path(config.get("path", f"./data/{self._table_name()}.csv"))
        self._file = None
        self._writer = None
        self._header_written = False

    async def open(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.file_path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=[])
        # 检查文件是否已有表头
        if self.file_path.stat().st_size > 0:
            self._header_written = True

    async def close(self):
        await self.flush()
        if self._file:
            self._file.close()

    async def _write_batch(self, items: list[dict]):
        if not items:
            return
        # 动态获取字段名
        fieldnames = list(items[0].keys())
        if not self._header_written or set(fieldnames) != set(self._writer.fieldnames):
            self._writer = csv.DictWriter(self._file, fieldnames=fieldnames)
            if not self._header_written:
                self._writer.writeheader()
                self._header_written = True
        self._writer.writerows(items)
        self._file.flush()
