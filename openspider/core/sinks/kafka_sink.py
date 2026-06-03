"""Kafka Sink — 发送到 Kafka topic"""

from __future__ import annotations

import json
import hashlib

from openspider.core.sinks.base import BaseSink


class KafkaSink(BaseSink):
    """将爬取数据发送到 Kafka topic"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.topic = config.get("topic", self._table_name())
        self.bootstrap_servers = config.get("bootstrap_servers", "localhost:9092")
        self.auto_create = config.get("auto_create", True)
        self.partitions = config.get("partitions", 3)
        self.replication_factor = config.get("replication_factor", 1)
        self._producer = None

    async def open(self):
        try:
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            await self._producer.start()
            # 自动创建 topic
            if self.auto_create:
                await self._ensure_topic()
        except ImportError:
            raise RuntimeError("aiokafka 未安装，请执行: pip install aiokafka")

    async def close(self):
        await self.flush()
        if self._producer:
            await self._producer.stop()

    async def _ensure_topic(self):
        """自动创建 Kafka topic（如不存在）"""
        try:
            from aiokafka.admin import AIOKafkaAdminClient, NewTopic
            admin = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
            await admin.start()
            try:
                existing = await admin.list_topics()
                if self.topic not in existing:
                    new_topic = NewTopic(
                        self.topic,
                        num_partitions=self.partitions,
                        replication_factor=self.replication_factor,
                    )
                    await admin.create_topics([new_topic])
            finally:
                await admin.close()
        except Exception:
            pass  # topic 可能已存在

    async def _write_batch(self, items: list[dict]):
        if not self._producer:
            return
        for item in items:
            # 主键 hash 作为消息 key
            key_fields = self.config.get("primary_key", [])
            if key_fields:
                key_str = "|".join(str(item.get(f, "")) for f in key_fields)
                msg_key = hashlib.md5(key_str.encode()).hexdigest()
            else:
                msg_key = None
            await self._producer.send_and_wait(self.topic, value=item, key=msg_key)
