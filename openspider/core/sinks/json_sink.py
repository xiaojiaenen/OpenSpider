"""JSON Sink — 写入 JSON/JSONL 文件"""

from __future__ import annotations

import json
from pathlib import Path

from openspider.core.sinks.base import BaseSink


class JsonSink(BaseSink):
    """将爬取数据写入 JSON 或 JSONL 文件"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.format = config.get("format", "jsonl")  # json 或 jsonl
        self.file_path = Path(config.get("path", f"./data/{self._table_name()}.{self.format}"))
        self._file = None

    async def open(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.file_path, "a", encoding="utf-8")

    async def close(self):
        await self.flush()
        if self._file:
            self._file.close()

    async def _write_batch(self, items: list[dict]):
        if self.format == "jsonl":
            for item in items:
                self._file.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            # JSON 数组格式，追加模式下不太合适，直接覆盖
            for item in items:
                self._file.write(json.dumps(item, ensure_ascii=False) + "\n")
        self._file.flush()
