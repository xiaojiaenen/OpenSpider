"""FastAPI 应用入口"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from openspider.config import settings
from openspider.core.engine import Engine

# 启动检查
if not settings.jwt_secret_key:
    import warnings
    warnings.warn(
        "jwt_secret_key 未设置！请在 .env 或环境变量中配置。",
        stacklevel=1,
    )
    settings.jwt_secret_key = "dev-insecure-key-change-me-in-production"

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
    description="爬虫管理平台",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from openspider.api.routes import router, public_router, set_engine
from openspider.api.auth_routes import auth_router
from openspider.api.schedule_routes import schedule_router
from openspider.api.error_handler import register_error_handlers
from openspider.api.websocket import ws_router

set_engine(engine)
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(router)
app.include_router(schedule_router)
app.include_router(ws_router)
register_error_handlers(app)

# 前端静态文件
_frontend_dir = settings.frontend_dir if hasattr(settings, "frontend_dir") else Path("./web/dist")
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


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