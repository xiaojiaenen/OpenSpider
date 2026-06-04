"""用户上下文 — 从 JWT 注入的 UserModel 提取"""

from __future__ import annotations

from fastapi import Depends

from openspider.api.auth import get_current_user
from openspider.models.user import UserModel


class UserContext:
    """用户上下文，贯穿请求生命周期"""

    def __init__(self, user: UserModel | None = None):
        self.user = user

    @property
    def user_id(self) -> str | None:
        return str(self.user.id) if self.user else None

    @property
    def username(self) -> str:
        return self.user.username if self.user else ""

    @property
    def is_admin(self) -> bool:
        return self.user is not None and self.user.role.value == "admin"


async def get_ctx(user: UserModel = Depends(get_current_user)) -> UserContext:
    """组合依赖：从 JWT 用户构建 UserContext"""
    return UserContext(user=user)
