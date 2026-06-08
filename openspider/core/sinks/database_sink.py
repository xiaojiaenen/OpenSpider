"""Database Sink — 动态建表 + 数据库存储"""

from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openspider.core.sinks.base import BaseSink


class DatabaseSink(BaseSink):
    """数据库输出

    根据 fields 定义动态创建数据表，支持 SQLite 和 MySQL。
    配置 dedup_key 后执行 UPSERT，否则追加。
    """

    STANDARD_COLUMNS = [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("user_id", "VARCHAR(128) NOT NULL"),
        ("task_id", "INTEGER NOT NULL"),
        ("url", "VARCHAR(2048) DEFAULT ''"),
        ("crawled_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]
    STANDARD_COLUMN_NAMES = {col[0] for col in STANDARD_COLUMNS}

    def __init__(self, config: dict):
        super().__init__(config)
        self.db_session_factory: async_sessionmaker = config["db_session_factory"]
        self.spider_id: int = config.get("spider_id", 0)
        self.fields: list[dict] = config.get("fields", [])
        self.dedup_key: list[str] | None = config.get("dedup_key")
        self.task_id: int = config.get("task_id", 0)
        self._table_checked = False

    @property
    def table_name(self) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", self.spider_name)
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return f"spider_{self.spider_id}_{sanitized}"

    async def open(self):
        async with self.db_session_factory() as session:
            conn = session.get_bind()
            is_sqlite = conn.dialect.name == "sqlite"
            if is_sqlite:
                await self._ensure_table_sqlite(session)
            else:
                await self._ensure_table_mysql(session)
            await session.commit()
        self._table_checked = True
        logger.debug(f"DatabaseSink: 数据表就绪 {self.table_name}")

    async def close(self):
        await self.flush()

    async def _write_batch(self, items: list[dict]):
        if not items:
            return
        for item in items:
            await self._save_one(item)

    async def _ensure_table_sqlite(self, session: AsyncSession):
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": self.table_name},
        )
        if result.scalar_one_or_none() is None:
            await self._create_table(session, is_sqlite=True)
        else:
            await self._add_missing_columns_sqlite(session)
        if self.dedup_key:
            idx_name = f"idx_{self.table_name}_dedup"
            cols = ", ".join(self.dedup_key)
            await session.execute(
                text(f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON {self.table_name} ({cols})")
            )

    async def _ensure_table_mysql(self, session: AsyncSession):
        result = await session.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name=:name AND table_schema=DATABASE()"),
            {"name": self.table_name},
        )
        if result.scalar_one() == 0:
            await self._create_table(session, is_sqlite=False)
        else:
            await self._add_missing_columns_mysql(session)
        if self.dedup_key:
            idx_name = f"idx_{self.table_name}_dedup"
            cols = ", ".join(self.dedup_key)
            try:
                await session.execute(text(f"CREATE UNIQUE INDEX {idx_name} ON {self.table_name} ({cols})"))
            except Exception:
                pass

    async def _create_table(self, session: AsyncSession, is_sqlite: bool):
        columns = []
        for col_name, col_type in self.STANDARD_COLUMNS:
            if not is_sqlite and "AUTOINCREMENT" in col_type.upper():
                col_type = "INT NOT NULL AUTO_INCREMENT PRIMARY KEY"
            elif not is_sqlite and col_type == "INTEGER":
                col_type = "INT"
            columns.append(f"`{col_name}` {col_type}")
        for field in self.fields:
            name = field["name"]
            ftype = field.get("type", "VARCHAR(512)")
            if name not in self.STANDARD_COLUMN_NAMES:
                columns.append(f"`{name}` {ftype}")
        sql = f"CREATE TABLE {self.table_name} (\n  " + ",\n  ".join(columns) + "\n)"
        await session.execute(text(sql))
        logger.info(f"DatabaseSink: 创建数据表 {self.table_name}（{len(columns)} 列）")
        await session.execute(text(f"CREATE INDEX idx_{self.table_name}_crawled ON {self.table_name} (crawled_at)"))
        await session.execute(text(f"CREATE INDEX idx_{self.table_name}_user ON {self.table_name} (user_id)"))

    async def _add_missing_columns_sqlite(self, session: AsyncSession):
        result = await session.execute(text(f"PRAGMA table_info({self.table_name})"))
        existing_cols = {row[1] for row in result.fetchall()}
        for field in self.fields:
            name = field["name"]
            ftype = field.get("type", "VARCHAR(512)")
            if name not in existing_cols and name not in self.STANDARD_COLUMN_NAMES:
                await session.execute(text(f"ALTER TABLE {self.table_name} ADD COLUMN `{name}` {ftype}"))

    async def _add_missing_columns_mysql(self, session: AsyncSession):
        result = await session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name=:name AND table_schema=DATABASE()"),
            {"name": self.table_name},
        )
        existing_cols = {row[0] for row in result.fetchall()}
        for field in self.fields:
            name = field["name"]
            ftype = field.get("type", "VARCHAR(512)")
            if name not in existing_cols and name not in self.STANDARD_COLUMN_NAMES:
                await session.execute(text(f"ALTER TABLE {self.table_name} ADD COLUMN `{name}` {ftype}"))

    async def _save_one(self, item: dict):
        url = item.get("url", "")
        params: dict = {"user_id": self.user_id, "task_id": self.task_id, "url": url}
        for field in self.fields:
            name = field["name"]
            if name not in self.STANDARD_COLUMN_NAMES and name in item:
                params[name] = item[name]
        if self.dedup_key:
            await self._upsert(params)
        else:
            await self._insert(params)

    async def _insert(self, params: dict):
        async with self.db_session_factory() as session:
            cols = {k: v for k, v in params.items() if k not in ("id", "crawled_at")}
            col_names = ", ".join(f"`{k}`" for k in cols.keys())
            placeholders = ", ".join([f":{k}" for k in cols.keys()])
            sql = f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders})"
            await session.execute(text(sql), cols)
            await session.commit()

    async def _upsert(self, params: dict):
        async with self.db_session_factory() as session:
            conn = session.get_bind()
            is_sqlite = conn.dialect.name == "sqlite"
            cols = {k: v for k, v in params.items() if k not in ("id", "crawled_at")}
            col_names = ", ".join(f"`{k}`" for k in cols.keys())
            placeholders = ", ".join([f":{k}" for k in cols.keys()])
            conflict_cols = ", ".join(f"`{k}`" for k in self.dedup_key)
            set_clause = ", ".join(f"`{k}` = :{k}" for k in cols.keys() if k not in self.dedup_key)
            if is_sqlite:
                sql = (
                    f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {set_clause}"
                )
            else:
                sql = (
                    f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders}) "
                    f"ON DUPLICATE KEY UPDATE {set_clause}"
                )
            await session.execute(text(sql), cols)
            await session.commit()

    async def truncate(self, user_id: str | None = None) -> int:
        async with self.db_session_factory() as session:
            if user_id:
                result = await session.execute(text(f"DELETE FROM {self.table_name} WHERE user_id = :user_id"), {"user_id": user_id})
            else:
                result = await session.execute(text(f"DELETE FROM {self.table_name}"))
            await session.commit()
            deleted = result.rowcount
            logger.info(f"DatabaseSink: 清空 {self.table_name} 删除 {deleted} 行")
            return deleted