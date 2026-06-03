"""用户上下文 — 从请求头提取 X-User-Id，实现数据隔离"""

from __future__ import annotations

from fastapi import Header, HTTPException

from openspider.config import settings


class UserContext:
    """用户上下文，贯穿整个请求生命周期"""

    def __init__(self, user_id: str | None, is_admin: bool = False):
        self.user_id = user_id
        self.is_admin = is_admin

    @property
    def table_prefix(self) -> str:
        """数据表前缀，用于隔离用户的爬取数据表"""
        if not self.user_id:
            return ""
        # 取 user_id 的安全字符作为前缀
        safe_id = self.user_id.replace("-", "")[:16]
        return f"u{safe_id}_"


def get_user_context(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> UserContext:
    """从请求头提取用户上下文

    - X-User-Id：普通用户，只能操作自己的资源
    - X-API-Key + admin key：管理员，可看所有
    """
    admin_key = getattr(settings, "admin_api_key", "")

    # 管理员 Key 优先
    if admin_key and x_api_key == admin_key:
        return UserContext(user_id=None, is_admin=True)

    # 普通用户
    if x_user_id:
        return UserContext(user_id=x_user_id, is_admin=False)

    # 都没有 — 共享模式（兼容无用户场景）
    return UserContext(user_id=None, is_admin=False)
