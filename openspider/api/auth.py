"""API 认证 — API Key 机制"""

from __future__ import annotations

from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader

from openspider.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> str | None:
    """从配置获取 API Key"""
    return getattr(settings, "api_key", None)


async def verify_api_key(api_key: str | None = Security(api_key_header)):
    """验证 API Key

    如果未配置 api_key，则跳过认证（开发模式）。
    如果配置了 api_key，则请求必须携带正确的 Key。
    """
    expected_key = get_api_key()

    # 未配置 Key，跳过认证（开发模式）
    if not expected_key:
        return True

    # 配置了 Key，必须验证
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="缺少 API Key，请在请求头中添加 X-API-Key",
        )

    if api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="API Key 无效",
        )

    return True
