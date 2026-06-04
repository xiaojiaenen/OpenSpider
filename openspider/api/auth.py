"""JWT 认证"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from openspider.models.user import UserModel, UserStatus
from openspider.storage.database import async_session
from openspider.utils.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserModel:
    """从 JWT 解码并查询用户"""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效或过期的 token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 token")

    async with async_session() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.id == int(user_id))
        )
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user.status == UserStatus.DISABLED:
        raise HTTPException(status_code=403, detail="账户已禁用")
    return user


async def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
