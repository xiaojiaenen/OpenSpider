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
        """添加一个 Sink

        Args:
            sink_config: Sink 配置，必须包含 type 字段
                示例: {"type": "csv", "path": "./data/out.csv"}
        """
        sink_type = sink_config.get("type")
        if not sink_type:
            raise ValueError("sink_config 必须包含 type 字段")

        sink_cls = get_sink_class(sink_type)
        if sink_cls is None:
            raise ValueError(f"未知的 sink 类型: {sink_type}")

        # 注入平台信息
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
    def from_spider(cls, spider, user_id: str | None = None) -> "Pipeline":
        """从爬虫实例创建 Pipeline

        读取 spider 的 sinks、schema、primary_key 属性。
        """
        pipeline = cls(
            spider_name=spider.name,
            user_id=user_id,
            primary_key=getattr(spider, "primary_key", []),
            schema=getattr(spider, "schema", None),
        )

        sinks_config = getattr(spider, "sinks", [])
        for sink_config in sinks_config:
            try:
                pipeline.add_sink(sink_config)
            except Exception as e:
                logger.error(f"Pipeline: 添加 sink 失败: {e}")

        return pipeline
