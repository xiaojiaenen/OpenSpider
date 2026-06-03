"""Doris Sink — 通过 HTTP Stream Load 写入 Doris"""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from openspider.core.sinks.base import BaseSink


# Python 类型 → Doris 类型映射
TYPE_MAP = {
    "string": "VARCHAR(500)",
    "text": "TEXT",
    "int": "BIGINT",
    "float": "DOUBLE",
    "datetime": "DATETIME",
    "bool": "BOOLEAN",
    "json": "JSON",
    "array": "TEXT",  # Doris ARRAY 需要特殊处理，用 TEXT 代替
}


class DorisSink(BaseSink):
    """通过 HTTP Stream Load 将数据写入 Doris"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.host = config.get("host", "localhost")
        self.http_port = config.get("http_port", 8030)
        self.user = config.get("user", "root")
        self.password = config.get("password", "")
        self.database = config.get("database", "crawl")
        self.table = config.get("table", self._table_name())
        self.auto_create = config.get("auto_create", True)
        self.schema = config.get("schema", {})
        self.primary_key = config.get("primary_key", [])
        self.duplicate_key = config.get("duplicate_key", self.primary_key[0] if self.primary_key else "")
        self.buckets = config.get("buckets", 4)
        self._client = None

    async def open(self):
        self._client = httpx.AsyncClient()
        if self.auto_create:
            await self._ensure_table()

    async def close(self):
        await self.flush()
        if self._client:
            await self._client.aclose()

    async def _ensure_table(self):
        """自动建表（如不存在）"""
        if not self.schema:
            return

        columns = []
        for field, type_ in self.schema.items():
            columns.append(f"`{field}` {TYPE_MAP.get(type_, 'VARCHAR(500)')}")

        # 平台字段
        columns.append("`_task_id` BIGINT")
        columns.append("`_crawl_time` DATETIME DEFAULT CURRENT_TIMESTAMP")
        columns.append("`_update_time` DATETIME DEFAULT CURRENT_TIMESTAMP")
        columns.append("`_spider_name` VARCHAR(128)")

        key_col = self.duplicate_key or list(self.schema.keys())[0]

        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.database}`.`{self.table}` (
            {','.join(columns)}
        ) DUPLICATE KEY(`{key_col}`)
        DISTRIBUTED BY HASH(`{key_col}`) BUCKETS {self.buckets}
        PROPERTIES("replication_num" = "1")
        """

        try:
            await self._execute_sql(ddl)
        except Exception:
            pass  # 表可能已存在

    async def _execute_sql(self, sql: str):
        """通过 Doris MySQL 协议执行 SQL（需要 pymysql）"""
        import asyncio
        import pymysql

        def _exec():
            conn = pymysql.connect(
                host=self.host,
                port=self.http_port + 30,  # Doris query_port = http_port + 30
                user=self.user,
                password=self.password,
                database=self.database,
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_exec)

    async def _write_batch(self, items: list[dict]):
        """通过 HTTP Stream Load 批量写入"""
        if not items or not self._client:
            return

        # 添加平台字段
        for item in items:
            item["_crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item["_update_time"] = item["_crawl_time"]
            item["_spider_name"] = self.spider_name

        # 转为 TSV 格式
        tsv_data = "\t".join(items[0].keys()) + "\n"
        for item in items:
            tsv_data += "\t".join(str(v) if v is not None else "\\N" for v in item.values()) + "\n"

        url = f"http://{self.host}:{self.http_port}/api/{self.database}/{self.table}/_stream_load"
        headers = {
            "format": "csv",
            "column_separator": "\t",
            "Expect": "100-continue",
        }

        try:
            resp = await self._client.put(
                url,
                content=tsv_data.encode("utf-8"),
                headers=headers,
                auth=(self.user, self.password),
            )
            return resp.json()
        except Exception:
            pass  # 写入失败不中断爬虫
