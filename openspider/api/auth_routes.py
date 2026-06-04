"""用户管理 API — 注册 / 登录 / 个人资料"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from openspider.api.auth import get_current_user
from openspider.models.user import UserModel, UserRole, UserStatus
from openspider.storage.database import async_session
from openspider.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ── 请求/响应模型 ──────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ── 路由 ──────────────────────────────────────────

@auth_router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest):
    """注册新用户"""
    # 用户名格式校验
    if not re.match(r"^[a-zA-Z0-9_-]+$", body.username):
        raise HTTPException(400, "用户名只能包含字母、数字、下划线和连字符")

    async with async_session() as session:
        # 检查用户名重复
        exists = await session.execute(
            select(UserModel).where(UserModel.username == body.username)
        )
        if exists.scalar_one_or_none():
            raise HTTPException(409, "用户名已存在")

        # 检查邮箱重复
        exists = await session.execute(
            select(UserModel).where(UserModel.email == body.email)
        )
        if exists.scalar_one_or_none():
            raise HTTPException(409, "邮箱已被注册")

        user = UserModel(
            username=body.username,
            email=body.email,
            password_hash=hash_password(body.password),
            display_name=body.display_name or body.username,
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    from openspider.config import settings
    return TokenResponse(
        access_token=create_access_token(user_id, "user"),
        refresh_token=create_refresh_token(user_id),
        expires_in=settings.jwt_access_expire_minutes * 60,
    )


@auth_router.post("/login", response_model=TokenResponse)
async def login(username: str, password: str):
    """登录（OAuth2 兼容，也接受 JSON body）"""
    async with async_session() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if user.status == UserStatus.DISABLED:
        raise HTTPException(403, "账户已禁用")

    from openspider.config import settings
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.jwt_access_expire_minutes * 60,
    )


@auth_router.post("/login/json", response_model=TokenResponse)
async def login_json(body: LoginRequest):
    """登录（JSON body 方式）"""
    return await login(body.username, body.password)


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """刷新 access_token"""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(401, "无效或过期的 refresh_token")

    user_id = int(payload["sub"])

    async with async_session() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user = result.scalar_one_or_none()

    if user is None or user.status == UserStatus.DISABLED:
        raise HTTPException(401, "用户不存在或已禁用")

    from openspider.config import settings
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.jwt_access_expire_minutes * 60,
    )


@auth_router.get("/me", response_model=UserInfo)
async def get_me(user: UserModel = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        status=user.status.value,
        created_at=str(user.created_at),
    )


@auth_router.put("/me", response_model=UserInfo)
async def update_me(
    body: UpdateProfileRequest,
    user: UserModel = Depends(get_current_user),
):
    """更新个人资料"""
    async with async_session() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.id == user.id)
        )
        u = result.scalar_one_or_none()
        if u is None:
            raise HTTPException(404, "用户不存在")

        if body.display_name is not None:
            u.display_name = body.display_name
        if body.email is not None:
            # 检查邮箱是否被其他人使用
            exists = await session.execute(
                select(UserModel).where(
                    UserModel.email == body.email,
                    UserModel.id != user.id,
                )
            )
            if exists.scalar_one_or_none():
                raise HTTPException(409, "邮箱已被其他用户使用")
            u.email = body.email

        await session.commit()
        await session.refresh(u)

    return UserInfo(
        id=u.id,
        username=u.username,
        email=u.email,
        display_name=u.display_name,
        role=u.role.value,
        status=u.status.value,
        created_at=str(u.created_at),
    )


@auth_router.put("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    user: UserModel = Depends(get_current_user),
):
    """修改密码"""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "旧密码不正确")

    async with async_session() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.id == user.id)
        )
        u = result.scalar_one_or_none()
        if u is None:
            raise HTTPException(404, "用户不存在")

        u.password_hash = hash_password(body.new_password)
        await session.commit()

    return {"success": True, "message": "密码已更新"}
