"""Pydantic 请求/响应模型"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# === 爬虫相关 ===

class SpiderInfo(BaseModel):
    """爬虫基本信息"""
    name: str
    description: str = ""
    schedule: str | None = None
    status: str = "idle"
    use_stealth: bool = False
    owner_user_id: str | None = None
    is_public: bool = False
    is_running: bool = False
    items_scraped: int = 0
    requests_made: int = 0
    errors_count: int = 0


class SpiderListResponse(BaseModel):
    """爬虫列表响应"""
    spiders: list[SpiderInfo]
    total: int


class SpiderStartRequest(BaseModel):
    """启动爬虫请求"""
    params: dict = {}  # 运行时参数


class SpiderActionResponse(BaseModel):
    """爬虫操作响应"""
    success: bool
    message: str
    task_id: int | None = None


class SpiderUploadResponse(BaseModel):
    """爬虫上传响应"""
    success: bool
    message: str
    registered_spiders: list[str] = []


class SpiderVisibilityRequest(BaseModel):
    """切换爬虫公开/私有"""
    is_public: bool


# === 任务相关 ===

class TaskInfo(BaseModel):
    """任务信息"""
    id: int
    spider_name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items_scraped: int = 0
    requests_made: int = 0
    errors_count: int = 0
    error_message: str | None = None
    params: dict | None = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: list[TaskInfo]
    total: int


# === 数据相关 ===

class SpiderDataResponse(BaseModel):
    """爬虫数据响应"""
    items: list[dict]
    total: int
    page: int = 1
    page_size: int = 50
    columns: list[str] = []


class SpiderFieldsResponse(BaseModel):
    """爬虫字段响应"""
    spider_id: int
    spider_name: str
    fields: list[dict]
    dedup_key: list[str] | None = None


# === 系统相关 ===

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    version: str
    mysql_connected: bool
    active_spiders: int = 0
    registered_spiders: int = 0


# === 日志相关 ===

class LogInfo(BaseModel):
    """日志信息"""
    id: int
    spider_name: str
    task_id: int | None = None
    level: str
    message: str
    created_at: datetime


class LogListResponse(BaseModel):
    """日志列表响应"""
    logs: list[LogInfo]
    total: int
