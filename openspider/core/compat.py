"""网站兼容层 — 编码处理、表单辅助、Frame 处理"""

from __future__ import annotations

from openspider.utils.encoding import detect_encoding, extract_meta_charset
from openspider.utils.form import (
    extract_form_fields,
    extract_hidden_fields,
    extract_asp_viewstate,
    merge_form_data,
)
from openspider.utils.url import strip_jsessionid, resolve_url


def handle_response_encoding(response, spider_encoding: str | None = None):
    """处理响应编码

    Args:
        response: Scrapling Response 对象
        spider_encoding: 爬虫手动指定的编码

    Returns:
        正确解码的文本内容
    """
    if spider_encoding:
        return response.body.decode(spider_encoding, errors="replace")

    # 从 Content-Type 头获取编码
    content_type = response.headers.get("content-type", "")
    declared = None
    if "charset=" in content_type.lower():
        import re
        match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
        if match:
            declared = match.group(1).strip()

    # 从 HTML meta 标签获取
    if not declared:
        declared = extract_meta_charset(response.body)

    encoding = detect_encoding(response.body, declared)
    return response.body.decode(encoding, errors="replace")


def extract_frames(response) -> list[str]:
    """提取页面中所有 frame/iframe 的 URL

    Args:
        response: Scrapling Response 对象

    Returns:
        frame URL 列表（已解析为绝对 URL）
    """
    urls = []

    # <frame src="...">
    for frame in response.css("frame"):
        src = frame.attrib.get("src", "")
        if src:
            urls.append(resolve_url(response.url, src))

    # <iframe src="...">
    for iframe in response.css("iframe"):
        src = iframe.attrib.get("src", "")
        if src:
            urls.append(resolve_url(response.url, src))

    return urls


def detect_meta_refresh(response) -> str | None:
    """检测 HTML meta refresh 重定向

    Args:
        response: Scrapling Response 对象

    Returns:
        重定向目标 URL，无则返回 None
    """
    import re
    for meta in response.css("meta[http-equiv='refresh']"):
        content = meta.attrib.get("content", "")
        match = re.search(r"url=([^;\s]+)", content, re.IGNORECASE)
        if match:
            return resolve_url(response.url, match.group(1))
    return None


def detect_jsp_session_from_response(response) -> str | None:
    """从响应中检测 JSP jsessionid

    从 URL 或 Set-Cookie 头中提取。

    Args:
        response: Scrapling Response 对象

    Returns:
        jsessionid 值，未找到返回 None
    """
    # 从 URL 中提取
    _, jsessionid = strip_jsessionid(response.url)
    if jsessionid:
        return jsessionid

    # 从 Cookie 中提取
    cookies = response.cookies
    if isinstance(cookies, dict):
        return cookies.get("JSESSIONID")

    return None
