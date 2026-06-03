"""全局错误处理"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger


def register_error_handlers(app: FastAPI) -> None:
    """注册全局错误处理器"""

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        return JSONResponse(
            status_code=403,
            content={"detail": f"权限不足: {exc}"},
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": f"文件不存在: {exc}"},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error(f"未处理的异常: {request.method} {request.url} - {type(exc).__name__}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"服务器内部错误: {type(exc).__name__}"},
        )
