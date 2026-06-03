"""FastAPI 应用入口"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from loguru import logger

from openspider.config import settings
from openspider.core.engine import Engine

# 配置 loguru
logger.remove()
logger.add(sys.stderr, level=settings.log_level, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
logger.add(str(settings.log_file), level=settings.log_level, rotation="10 MB", retention="7 days")

# 全局引擎实例
engine = Engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("OpenSpider 启动中...")
    await engine.initialize()
    yield
    logger.info("OpenSpider 关闭中...")
    await engine.shutdown()


app = FastAPI(
    title="OpenSpider",
    description="爬虫管理平台 — 管理多个爬虫的生命周期，暴露标准化 API 供外部 AI 集成",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册路由
from openspider.api.routes import router, public_router, set_engine

set_engine(engine)
app.include_router(public_router)  # 不需要认证的接口
app.include_router(router)         # 需要认证的接口


def serve(host: str = None, port: int = None):
    """启动 API 服务"""
    uvicorn.run(
        "openspider.main:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    serve()
