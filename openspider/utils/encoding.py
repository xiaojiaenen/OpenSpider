"""编码检测 — 封装 charset-normalizer"""

from __future__ import annotations

import re

from charset_normalizer import from_bytes


def detect_encoding(raw_bytes: bytes, declared_charset: str | None = None) -> str:
    """检测响应编码

    优先级：
    1. 手动指定的编码（declared_charset）
    2. charset-normalizer 统计推断
    3. 回退 UTF-8

    Args:
        raw_bytes: 原始响应字节
        declared_charset: 声明的编码（来自 HTTP 头或 HTML meta 标签）

    Returns:
        检测到的编码名称
    """
    if declared_charset:
        return _normalize_encoding(declared_charset)

    # 使用 charset-normalizer 推断
    results = from_bytes(raw_bytes)
    if results:
        best = results.best()
        if best:
            return best.encoding

    return "utf-8"


def extract_meta_charset(html_bytes: bytes) -> str | None:
    """从 HTML meta 标签中提取编码声明

    支持：
    - <meta charset="gbk">
    - <meta http-equiv="Content-Type" content="text/html; charset=gbk">

    Args:
        html_bytes: HTML 响应字节

    Returns:
        编码名称，未找到返回 None
    """
    # 只检查前 2048 字节
    head = html_bytes[:2048]

    try:
        head_str = head.decode("ascii", errors="ignore")
    except Exception:
        return None

    # <meta charset="xxx">
    match = re.search(r'<meta[^>]+charset=["\']?([^"\'\s;>]+)', head_str, re.IGNORECASE)
    if match:
        return _normalize_encoding(match.group(1))

    # <meta http-equiv="Content-Type" content="...; charset=xxx">
    match = re.search(
        r'<meta[^>]+http-equiv=["\']Content-Type["\'][^>]+content=["\'][^"\']*charset=([^"\'\s;]+)',
        head_str, re.IGNORECASE
    )
    if match:
        return _normalize_encoding(match.group(1))

    return None


def _normalize_encoding(encoding: str) -> str:
    """标准化编码名称"""
    encoding = encoding.strip().lower()
    # 常见别名映射
    aliases = {
        "gb2312": "gbk",
        "gb_2312": "gbk",
        "cn-gb": "gbk",
        "euc-cn": "gbk",
        "big5": "big5",
        "big-5": "big5",
        "shift_jis": "shift_jis",
        "shift-jis": "shift_jis",
        "sjis": "shift_jis",
        "euc-jp": "euc_jp",
        "euc-kr": "euc_kr",
        "iso-8859-1": "latin-1",
        "latin1": "latin-1",
    }
    return aliases.get(encoding, encoding)
