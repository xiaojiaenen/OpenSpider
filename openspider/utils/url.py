"""URL 处理 — 规范化、jsessionid 剥离、相对 URL 拼接"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode


def normalize_url(url: str) -> str:
    """规范化 URL

    - 排序查询参数
    - 标准化路径
    - 去除默认端口
    """
    parsed = urlparse(url)
    # 排序查询参数
    params = parse_qs(parsed.query, keep_blank_values=True)
    sorted_query = urlencode(sorted(params.items()), doseq=True)
    # 标准化路径
    path = parsed.path or "/"
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        sorted_query,
        "",  # 去除 fragment
    ))


def strip_jsessionid(url: str) -> tuple[str, str | None]:
    """从 URL 中剥离 jsessionid

    Args:
        url: 可能包含 ;jsessionid=xxx 的 URL

    Returns:
        (清理后的 URL, jsessionid 值或 None)
    """
    match = re.search(r";jsessionid=([^;\s]+)", url, re.IGNORECASE)
    if match:
        jsessionid = match.group(1)
        clean_url = url[:match.start()] + url[match.end():]
        return clean_url, jsessionid
    return url, None


def resolve_url(base_url: str, relative_url: str) -> str:
    """将相对 URL 解析为绝对 URL

    Args:
        base_url: 基础 URL
        relative_url: 相对 URL

    Returns:
        绝对 URL
    """
    return urljoin(base_url, relative_url)


def extract_domain(url: str) -> str:
    """从 URL 中提取域名"""
    return urlparse(url).netloc


def is_same_domain(url1: str, url2: str) -> bool:
    """判断两个 URL 是否同域"""
    return extract_domain(url1) == extract_domain(url2)


def strip_fragment(url: str) -> str:
    """去除 URL 的 fragment 部分"""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))
