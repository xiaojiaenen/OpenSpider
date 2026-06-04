"""Parquet Sink — 通过 pandas 写入 Parquet 格式"""

from __future__ import annotations

import os

from loguru import logger

from openspider.core.sinks.base import BaseSink


class ParquetSink(BaseSink):
    """Parquet 文件输出

    依赖: pip install pandas pyarrow
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._path = config.get("path", "./data/output.parquet")
        self._buffer: list[dict] = []
        self._flush_interval = config.get("flush_interval", 1000)

    async def open(self):
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        logger.info(f"ParquetSink opened: {self._path}")

    async def write(self, item: dict):
        self._buffer.append(item)
        if len(self._buffer) >= self._flush_interval:
            await self.flush()

    async def flush(self):
        if not self._buffer:
            return
        try:
            import pandas as pd
            import pyarrow as pa
            import pyarrow.parquet as pq

            df = pd.DataFrame(self._buffer)

            if os.path.exists(self._path):
                existing = pd.read_parquet(self._path)
                df = pd.concat([existing, df], ignore_index=True)
                if self._primary_key:
                    df = df.drop_duplicates(subset=self._primary_key, keep="last")

            df.to_parquet(self._path, index=False)
            logger.info(f"ParquetSink: wrote {len(self._buffer)} items to {self._path}")
            self._buffer.clear()
        except ImportError:
            logger.error("ParquetSink 需要 pandas 和 pyarrow: pip install pandas pyarrow")
            self._buffer.clear()
        except Exception as e:
            logger.error(f"ParquetSink flush failed: {e}")

    async def close(self):
        await self.flush()
