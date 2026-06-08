"""Spider 数据管理器 — 动态建表 + CRUD 操作

为每个爬虫创建独立的数据表，支持动态字段定义、去重键、分页查询和数据导出。
同时兼容 SQLite 和 MySQL 两种数据库方言。
"""

from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# ── SQL 注入防护：标识符/类型校验 ─────────────────────────

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_VALID_TYPE_RE = re.compile(
    r"^(VARCHAR|CHAR|TEXT|INTEGER|INT|BIGINT|SMALLINT|FLOAT|DOUBLE|"
    r"DECIMAL|NUMERIC|BOOLEAN|BOOL|DATE|DATETIME|TIMESTAMP|BLOB|JSON|"
    r"REAL|SERIAL|INT NOT NULL AUTO_INCREMENT PRIMARY KEY|"
    r"INTEGER PRIMARY KEY AUTOINCREMENT|DEFAULT)\b",
    re.IGNORECASE,
)

_SQL_RESERVED = frozenset({
    "select", "insert", "update", "delete", "drop", "table", "column",
    "index", "from", "where", "or", "and", "null", "create", "alter",
    "grant", "revoke", "union", "join", "set", "into", "values",
})


def _validate_identifier(name: str, context: str = "column") -> str:
    """校验 SQL 标识符，不合法则抛 ValueError"""
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"非法{context}名: {name!r}（只允许字母数字下划线，不以数字开头）")
    if len(name) > 64:
        raise ValueError(f"{context}名过长: {name!r}")
    if name.lower() in _SQL_RESERVED:
        raise ValueError(f"{context}名是 SQL 保留字: {name!r}")
    return name


def _validate_column_type(ctype: str) -> str:
    """校验列类型，只允许白名单内的类型关键字"""
    if not ctype or not _VALID_TYPE_RE.match(ctype.strip()):
        raise ValueError(f"非法列类型: {ctype!r}")
    for ch in (";", "--", "/*", "*/", "'", '"', "(", ")"):
        if ch in ctype:
            raise ValueError(f"列类型含非法字符: {ctype!r}")
    return ctype


class SpiderDataManager:
    """爬虫数据管理器

    根据爬虫的 fields 定义动态创建/扩展数据表，并提供增删查改能力。

    每个爬虫拥有独立的数据表：spider_{spider_id}_{spider_name}
    表结构包含固定标准列 + 自定义字段列。

    Args:
        db_session_factory: 异步会话工厂（async_sessionmaker）
        spider_id: 爬虫 ID
        spider_name: 爬虫名称（用于表名）
        fields: 字段定义列表，格式 [{'name': 'title', 'type': 'VARCHAR(512)'}, ...]
        dedup_key: 去重键字段列表，有值则 upsert，无值则追加
    """

    # 标准列定义（固定存在，不可被 fields 覆盖）
    STANDARD_COLUMNS = [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("user_id", "VARCHAR(128) NOT NULL"),
        ("task_id", "INTEGER NOT NULL"),
        ("url", "VARCHAR(2048) DEFAULT ''"),
        ("crawled_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]

    STANDARD_COLUMN_NAMES = {col[0] for col in STANDARD_COLUMNS}

    def __init__(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        spider_id: int,
        spider_name: str,
        fields: list[dict],
        dedup_key: list[str] | None = None,
    ):
        self.db_session_factory = db_session_factory
        self.spider_id = spider_id
        self.spider_name = spider_name
        self.fields = fields or []
        self.dedup_key = dedup_key
        self._table_checked = False  # 缓存表结构检查结果

    # ------------------------------------------------------------------
    #  表名
    # ------------------------------------------------------------------

    @property
    def table_name(self) -> str:
        """返回数据表名：spider_{spider_id}_{sanitized_name}

        表名规则：
        - 前缀 spider_ + 爬虫 ID + 下划线 + 爬虫名称
        - 名称中非字母数字字符替换为下划线
        - 多个连续下划线合并为一个
        - 去除首尾下划线（前缀除外）
        """
        sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", self.spider_name)
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return f"spider_{self.spider_id}_{sanitized}"

    # ------------------------------------------------------------------
    #  Dialect 工具
    # ------------------------------------------------------------------

    def _is_sqlite(self, conn) -> bool:
        """检测当前连接是否为 SQLite"""
        return conn.dialect.name == "sqlite"

    def _col_type_mysql(self, col_type: str) -> str:
        """将 SQLite 风格类型转换为 MySQL 兼容类型

        SQLite 的 INTEGER PRIMARY KEY AUTOINCREMENT 在 MySQL 中需要
        转换为对应的 INT AUTO_INCREMENT PRIMARY KEY。
        """
        upper = col_type.upper()
        if "INTEGER PRIMARY KEY AUTOINCREMENT" in upper:
            return "INT NOT NULL AUTO_INCREMENT PRIMARY KEY"
        if upper == "INTEGER":
            return "INT"
        return col_type

    # ------------------------------------------------------------------
    #  ensure_table
    # ------------------------------------------------------------------

    async def ensure_table(self) -> None:
        """确保数据表存在且结构完整

        - 表不存在 → CREATE TABLE + 建索引
        - 表存在   → 检查缺失列，ALTER TABLE ADD COLUMN 补齐
        - dedup_key → 创建唯一索引
        """
        async with self.db_session_factory() as session:
            conn = await session.get_bind()
            is_sqlite = self._is_sqlite(conn)

            if is_sqlite:
                await self._ensure_table_sqlite(session)
            else:
                await self._ensure_table_mysql(session)

            await session.commit()
            self._table_checked = True
            logger.debug(f"数据表就绪: {self.table_name}")

    async def _ensure_table_sqlite(self, session: AsyncSession) -> None:
        """SQLite 建表/补列"""
        # 检查表是否存在
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": self.table_name},
        )
        table_exists = result.scalar_one_or_none() is not None

        if not table_exists:
            await self._create_table(session)
        else:
            await self._add_missing_columns_sqlite(session)

        # 建索引（幂等）
        if self.dedup_key:
            for k in self.dedup_key:
                _validate_identifier(k, "去重键")
            idx_name = f"idx_{self.table_name}_dedup"
            cols = ", ".join(self.dedup_key)
            await session.execute(
                text(f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON {self.table_name} ({cols})")
            )

    async def _ensure_table_mysql(self, session: AsyncSession) -> None:
        """MySQL 建表/补列"""
        result = await session.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name=:name AND table_schema=DATABASE()"),
            {"name": self.table_name},
        )
        table_exists = result.scalar_one() > 0

        if not table_exists:
            await self._create_table(session)
        else:
            await self._add_missing_columns_mysql(session)

        if self.dedup_key:
            for k in self.dedup_key:
                _validate_identifier(k, "去重键")
            idx_name = f"idx_{self.table_name}_dedup"
            cols = ", ".join(self.dedup_key)
            # MySQL: 先检查索引是否存在，再创建
            try:
                await session.execute(
                    text(f"CREATE UNIQUE INDEX {idx_name} ON {self.table_name} ({cols})")
                )
            except Exception:
                # 索引已存在，忽略
                pass

    async def _create_table(self, session: AsyncSession) -> None:
        """创建完整的数据表"""
        conn = await session.get_bind()
        is_sqlite = self._is_sqlite(conn)

        columns = []
        for col_name, col_type in self.STANDARD_COLUMNS:
            if is_sqlite:
                columns.append(f"{col_name} {col_type}")
            else:
                columns.append(f"{col_name} {self._col_type_mysql(col_type)}")

        # 自定义字段
        for field in self.fields:
            name = _validate_identifier(field["name"], "字段")
            ftype = _validate_column_type(field.get("type", "VARCHAR(512)"))
            if not is_sqlite:
                ftype = self._col_type_mysql(ftype)
            # 防止自定义字段覆盖标准列
            if name not in self.STANDARD_COLUMN_NAMES:
                columns.append(f"{name} {ftype}")

        create_sql = f"CREATE TABLE {self.table_name} (\n  " + ",\n  ".join(columns) + "\n)"
        await session.execute(text(create_sql))
        logger.info(f"创建数据表: {self.table_name}（{len(columns)} 列）")

        # 建索引
        await session.execute(
            text(f"CREATE INDEX idx_{self.table_name}_crawled ON {self.table_name} (crawled_at)")
        )
        await session.execute(
            text(f"CREATE INDEX idx_{self.table_name}_user ON {self.table_name} (user_id)")
        )

    async def _add_missing_columns_sqlite(self, session: AsyncSession) -> None:
        """SQLite: 获取现有列，补全缺失列"""
        result = await session.execute(
            text(f"PRAGMA table_info({self.table_name})")
        )
        existing_cols = {row[1] for row in result.fetchall()}

        for field in self.fields:
            name = _validate_identifier(field["name"], "字段")
            ftype = _validate_column_type(field.get("type", "VARCHAR(512)"))
            if name not in existing_cols and name not in self.STANDARD_COLUMN_NAMES:
                await session.execute(
                    text(f"ALTER TABLE {self.table_name} ADD COLUMN {name} {ftype}")
                )
                logger.info(f"补充列: {self.table_name}.{name}")

    async def _add_missing_columns_mysql(self, session: AsyncSession) -> None:
        """MySQL: 通过 information_schema 获取现有列，补全缺失列"""
        result = await session.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name=:name AND table_schema=DATABASE()"),
            {"name": self.table_name},
        )
        existing_cols = {row[0] for row in result.fetchall()}

        for field in self.fields:
            name = _validate_identifier(field["name"], "字段")
            ftype = _validate_column_type(field.get("type", "VARCHAR(512)"))
            ftype_mysql = self._col_type_mysql(ftype)
            if name not in existing_cols and name not in self.STANDARD_COLUMN_NAMES:
                await session.execute(
                    text(f"ALTER TABLE {self.table_name} ADD COLUMN {name} {ftype_mysql}")
                )
                logger.info(f"补充列: {self.table_name}.{name}")

    # ------------------------------------------------------------------
    #  save_item
    # ------------------------------------------------------------------

    async def save_item(self, item: dict, user_id: str, task_id: int) -> None:
        """保存一条数据项

        如果 dedup_key 已设置，执行 UPSERT（INSERT ... ON CONFLICT DO UPDATE）；
        否则执行普通 INSERT。

        Args:
            item: 数据字典，key 为字段名，value 为字段值
            user_id: 用户 ID
            task_id: 任务 ID
        """
        # 提取标准字段
        url = item.get("url", "")

        # 提取自定义字段值（排除标准字段名冲突）
        custom_fields = {}
        for field in self.fields:
            name = field["name"]
            if name not in self.STANDARD_COLUMN_NAMES and name in item:
                custom_fields[name] = item[name]

        # 合并参数
        params: dict = {
            "user_id": user_id,
            "task_id": task_id,
            "url": url,
        }
        params.update(custom_fields)

        # 构建 SQL
        if self.dedup_key:
            await self._upsert(params)
        else:
            await self._insert(params)

    async def _insert(self, params: dict) -> None:
        """普通 INSERT"""
        async with self.db_session_factory() as session:
            conn = await session.get_bind()
            is_sqlite = self._is_sqlite(conn)

            # 不插入 id（自增）和 crawled_at（默认值）
            cols = {k: v for k, v in params.items() if k not in ("id", "crawled_at")}
            # 校验所有列名
            for k in cols:
                _validate_identifier(k, "列名")
            col_names = ", ".join(cols.keys())
            placeholders = ", ".join([f":{k}" for k in cols.keys()])

            sql = f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders})"
            await session.execute(text(sql), cols)
            await session.commit()

    async def _upsert(self, params: dict) -> None:
        """UPSERT: INSERT ... ON CONFLICT DO UPDATE"""
        async with self.db_session_factory() as session:
            conn = await session.get_bind()
            is_sqlite = self._is_sqlite(conn)

            # 不插入 id 和 crawled_at
            cols = {k: v for k, v in params.items() if k not in ("id", "crawled_at")}
            # 校验所有列名和 dedup_key
            for k in cols:
                _validate_identifier(k, "列名")
            for k in (self.dedup_key or []):
                _validate_identifier(k, "去重键")
            col_names = ", ".join(cols.keys())
            placeholders = ", ".join([f":{k}" for k in cols.keys()])

            # ON CONFLICT 列（dedup_key）
            conflict_cols = ", ".join(self.dedup_key)

            # SET 子句：排除 dedup_key 和 user_id/task_id（这些不更新）
            update_parts = []
            for k in cols.keys():
                if k not in self.dedup_key:
                    update_parts.append(f"{k} = :{k}")
            set_clause = ", ".join(update_parts)

            if is_sqlite:
                # SQLite: INSERT OR REPLACE 或 ON CONFLICT
                sql = (
                    f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {set_clause}"
                )
            else:
                # MySQL: INSERT ... ON DUPLICATE KEY UPDATE
                sql = (
                    f"INSERT INTO {self.table_name} ({col_names}) VALUES ({placeholders}) "
                    f"ON DUPLICATE KEY UPDATE {set_clause}"
                )

            await session.execute(text(sql), cols)
            await session.commit()

    # ------------------------------------------------------------------
    #  query
    # ------------------------------------------------------------------

    async def query(
        self,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        filters: dict | None = None,
    ) -> dict:
        """分页查询数据

        Args:
            user_id: 用户 ID 过滤（可选）
            page: 页码，从 1 开始
            page_size: 每页条数
            filters: 额外的过滤条件 {column_name: value}

        Returns:
            {"items": [row_dict, ...], "total": int}
        """
        where_parts = ["1=1"]
        bind_params: dict = {}

        if user_id is not None:
            where_parts.append("user_id = :user_id")
            bind_params["user_id"] = user_id

        if filters:
            for key, value in filters.items():
                # 白名单：只允许已知列名，防止 SQL 注入
                _validate_identifier(key, "查询字段")
                if key in self.STANDARD_COLUMN_NAMES or any(f["name"] == key for f in self.fields):
                    where_parts.append(f"{key} = :filter_{key}")
                    bind_params[f"filter_{key}"] = value

        where_sql = " AND ".join(where_parts)
        offset = (max(page, 1) - 1) * page_size

        async with self.db_session_factory() as session:
            # 总数
            count_sql = f"SELECT COUNT(*) AS cnt FROM {self.table_name} WHERE {where_sql}"
            result = await session.execute(text(count_sql), bind_params)
            total = result.scalar_one()

            # 分页数据
            data_sql = (
                f"SELECT * FROM {self.table_name} "
                f"WHERE {where_sql} "
                f"ORDER BY crawled_at DESC "
                f"LIMIT :limit OFFSET :offset"
            )
            query_params = {**bind_params, "limit": page_size, "offset": offset}
            result = await session.execute(text(data_sql), query_params)
            rows = result.mappings().all()

        return {
            "items": [dict(row) for row in rows],
            "total": total,
        }

    # ------------------------------------------------------------------
    #  count
    # ------------------------------------------------------------------

    async def count(self, user_id: str | None = None) -> int:
        """统计数据行数

        Args:
            user_id: 用户 ID 过滤（可选）

        Returns:
            总行数
        """
        where_parts = ["1=1"]
        bind_params: dict = {}

        if user_id is not None:
            where_parts.append("user_id = :user_id")
            bind_params["user_id"] = user_id

        where_sql = " AND ".join(where_parts)

        async with self.db_session_factory() as session:
            sql = f"SELECT COUNT(*) FROM {self.table_name} WHERE {where_sql}"
            result = await session.execute(text(sql), bind_params)
            return result.scalar_one()

    # ------------------------------------------------------------------
    #  export
    # ------------------------------------------------------------------

    async def export(
        self,
        user_id: str | None = None,
        limit: int = 10000,
    ) -> list[dict]:
        """导出数据

        Args:
            user_id: 用户 ID 过滤（可选）
            limit: 最大导出条数（防 OOM）

        Returns:
            数据列表
        """
        where_parts = ["1=1"]
        bind_params: dict = {}

        if user_id is not None:
            where_parts.append("user_id = :user_id")
            bind_params["user_id"] = user_id

        where_sql = " AND ".join(where_parts)

        async with self.db_session_factory() as session:
            sql = (
                f"SELECT * FROM {self.table_name} "
                f"WHERE {where_sql} "
                f"ORDER BY crawled_at DESC "
                f"LIMIT :limit"
            )
            bind_params["limit"] = limit
            result = await session.execute(text(sql), bind_params)
            rows = result.mappings().all()

        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    def get_field_names(self) -> list[str]:
        """返回所有字段名（标准 + 自定义）"""
        standard = [col[0] for col in self.STANDARD_COLUMNS]
        custom = [f["name"] for f in self.fields if f["name"] not in self.STANDARD_COLUMN_NAMES]
        return standard + custom

    def __repr__(self) -> str:
        return (
            f"SpiderDataManager(spider_id={self.spider_id}, "
            f"table={self.table_name}, "
            f"fields={len(self.fields)}, "
            f"dedup_key={self.dedup_key})"
        )
