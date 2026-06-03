"""WebSocket 实时状态推送"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

ws_router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(f"WebSocket 已连接，当前 {len(self._connections)} 个客户端")

    def disconnect(self, websocket: WebSocket):
        self._connections.remove(websocket)
        logger.info(f"WebSocket 已断开，当前 {len(self._connections)} 个客户端")

    async def broadcast(self, data: dict[str, Any]):
        """向所有连接的客户端广播消息"""
        message = json.dumps(data, ensure_ascii=False, default=str)
        disconnected = []
        for conn in self._connections:
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            self._connections.remove(conn)


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点

    客户端连接后，每 5 秒推送一次爬虫状态。
    客户端发送 "ping" 返回 "pong"。
    """
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # 超时，推送状态更新
                await _push_status(websocket)
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)


async def _push_status(websocket: WebSocket):
    """推送当前爬虫状态"""
    from openspider.main import engine
    try:
        spiders = []
        for name, cls in engine.registry.spiders.items():
            status_info = engine.get_spider_status(name)
            spiders.append({
                "name": name,
                "is_running": status_info["is_running"] if status_info else False,
                "items_scraped": status_info["items_scraped"] if status_info else 0,
            })
        await websocket.send_text(json.dumps({
            "type": "status",
            "spiders": spiders,
            "total": len(spiders),
        }, ensure_ascii=False))
    except Exception:
        pass


async def broadcast_event(event_type: str, data: dict):
    """广播事件（供 Engine 调用）"""
    await manager.broadcast({
        "type": event_type,
        **data,
    })
