"""数据管道引擎 — 分发爬取数据到多个 Sink"""

from __future__ import annotations

from loguru import logger

from openspider.core.sinks import get_sink_class, BaseSink


class Pipeline:
    """数据管道

    管理多个 Sink，将爬取数据分发到各目标存储。
    """

    def __init__(self, spider_name: str, user_id: str | None = None,
                 primary_key: list[str] | None = None, schema: dict | None = None):
        self.spider_name = spider_name
        self.user_id = user_id
        self.primary_key = primary_key or []
        self.schema = schema
        self._sinks: list[BaseSink] = []

    def add_sink(self, sink_config: dict):
        """添加一个 Sink"""
        sink_type = sink_config.get("type")
        if not sink_type:
            raise ValueError("sink_config 必须包含 type 字段")

        sink_cls = get_sink_class(sink_type)
        if sink_cls is None:
            raise ValueError(f"未知的 sink 类型: {sink_type}")

        config = {**sink_config}
        config.setdefault("spider_name", self.spider_name)
        config.setdefault("user_id", self.user_id or "")
        config.setdefault("primary_key", self.primary_key)
        config.setdefault("schema", self.schema or {})

        sink = sink_cls(config)
        self._sinks.append(sink)
        logger.info(f"Pipeline: 添加 sink {sink_type} -> {sink_config.get('path', sink_config.get('topic', 'default'))}")

    async def open(self):
        """初始化所有 Sink"""
        for sink in self._sinks:
            try:
                await sink.open()
            except Exception as e:
                logger.error(f"Pipeline: sink 初始化失败: {e}")

    async def close(self):
        """关闭所有 Sink"""
        for sink in self._sinks:
            try:
                await sink.close()
            except Exception as e:
                logger.error(f"Pipeline: sink 关闭失败: {e}")

    async def process(self, item: dict):
        """将一条数据分发到所有 Sink"""
        for sink in self._sinks:
            try:
                await sink.write(item)
            except Exception as e:
                logger.error(f"Pipeline: 写入失败 ({sink.__class__.__name__}): {e}")

    async def flush(self):
        """刷新所有 Sink 缓冲区"""
        for sink in self._sinks:
            try:
                await sink.flush()
            except Exception as e:
                logger.error(f"Pipeline: flush 失败 ({sink.__class__.__name__}): {e}")

    @classmethod
    def from_spider(cls, spider, user_id: str | None = None,
                    db_session_factory=None, spider_id: int = 0,
                    task_id: int = 0) -> "Pipeline":
        """从爬虫实例创建 Pipeline

        如果用户配置了 sinks，只使用用户配置的 sinks；
        否则如果定义了 fields，自动添加 DatabaseSink 作为默认存储。
        """
        pipeline = cls(
            spider_name=spider.name,
            user_id=user_id,
            primary_key=getattr(spider, "primary_key", []),
            schema=getattr(spider, "schema", None),
        )

        user_sinks = getattr(spider, "sinks", [])

        if user_sinks:
            # 用户配置了 sinks → 只使用用户配置的 sinks
            for sink_config in user_sinks:
                try:
                    pipeline.add_sink(sink_config)
                except Exception as e:
                    logger.error(f"Pipeline: 添加 sink 失败: {e}")
        else:
            # 未配置 sinks → 使用默认 DatabaseSink
            fields = getattr(spider, "fields", [])
            if fields and db_session_factory and spider_id:
                from openspider.core.sinks.database_sink import DatabaseSink
                db_sink = DatabaseSink({
                    "spider_name": spider.name,
                    "user_id": user_id or "",
                    "db_session_factory": db_session_factory,
                    "spider_id": spider_id,
                    "task_id": task_id,
                    "fields": fields,
                    "dedup_key": getattr(spider, "dedup_key", None),
                })
                pipeline._sinks.append(db_sink)
                logger.info(f"Pipeline: 自动添加 DatabaseSink -> {db_sink.table_name}")

        return pipeline

    @classmethod
    def from_config(
        cls,
        spider_name: str,
        user_id: str | None = None,
        primary_key: list[str] | None = None,
        schema: dict | None = None,
        sinks: list[dict] | None = None,
    ) -> "Pipeline":
        """从配置参数创建 Pipeline（不依赖爬虫实例）

        用于沙箱模式：主进程中不需要实例化爬虫。
        """
        pipeline = cls(
            spider_name=spider_name,
            user_id=user_id,
            primary_key=primary_key,
            schema=schema,
        )

        for sink_config in (sinks or []):
            try:
                pipeline.add_sink(sink_config)
            except Exception as e:
                logger.error(f"Pipeline: 添加 sink 失败: {e}")

        return pipeline
