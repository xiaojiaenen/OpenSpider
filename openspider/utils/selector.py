"""选择器增强 — 自适应爬取、增强元素查找、选择器生成"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapling.operators import Response


def find_by_text(response, text: str, tag: str | None = None,
                 partial: bool = False, case_sensitive: bool = False,
                 first_match: bool = True):
    """按文本内容查找元素

    Args:
        response: Scrapling Response 对象
        text: 要查找的文本
        tag: 限定标签名（可选）
        partial: 是否模糊匹配
        case_sensitive: 是否区分大小写
        first_match: 是否只返回第一个匹配

    Returns:
        匹配的元素或元素列表
    """
    result = response.find_by_text(
        text,
        tag=tag,
        partial=partial,
        case_sensitive=case_sensitive,
        first_match=first_match,
    )
    return result


def find_by_regex(response, pattern, first_match: bool = True):
    """按正则表达式匹配元素文本内容

    Args:
        response: Scrapling Response 对象
        pattern: 正则表达式（字符串或编译后的 Pattern）
        first_match: 是否只返回第一个匹配

    Returns:
        匹配的元素或元素列表
    """
    return response.find_by_regex(pattern, first_match=first_match)


def find_similar(response, element, similarity_threshold: float = 0.2,
                 ignore_attributes: list[str] | None = None,
                 match_text: bool = False):
    """查找页面上与给定元素结构相似的所有元素

    Args:
        response: Scrapling Response 对象
        element: 参考元素
        similarity_threshold: 相似度阈值（0-1）
        ignore_attributes: 忽略的属性名列表
        match_text: 是否匹配文本内容

    Returns:
        相似元素列表
    """
    if ignore_attributes is None:
        ignore_attributes = ["href", "src"]
    return element.find_similar(
        similarity_threshold=similarity_threshold,
        ignore_attributes=ignore_attributes,
        match_text=match_text,
    )


def generate_css_selector(element, full: bool = False) -> str:
    """为元素生成 CSS 选择器

    Args:
        element: 目标元素
        full: 是否生成从根节点开始的完整选择器

    Returns:
        CSS 选择器字符串
    """
    if full:
        return element.generate_full_css_selector
    return element.generate_css_selector


def generate_xpath_selector(element, full: bool = False) -> str:
    """为元素生成 XPath 选择器

    Args:
        element: 目标元素
        full: 是否生成从根节点开始的完整选择器

    Returns:
        XPath 选择器字符串
    """
    if full:
        return element.generate_full_xpath_selector
    return element.generate_xpath_selector


def auto_select(response, selector: str, css: bool = True,
                adaptive: bool = False, auto_save: bool = False,
                adaptive_domain: str | None = None):
    """统一选择器方法，支持自适应

    Args:
        response: Scrapling Response 对象
        selector: CSS 或 XPath 选择器
        css: True 为 CSS 选择器，False 为 XPath
        adaptive: 启用自适应模式
        auto_save: 自动保存元素属性
        adaptive_domain: 自适应域名覆盖

    Returns:
        选择结果
    """
    kwargs = {}
    if adaptive:
        kwargs["adaptive"] = True
    if auto_save:
        kwargs["auto_save"] = True
    if adaptive_domain:
        kwargs["adaptive_domain"] = adaptive_domain

    if css:
        return response.css(selector, **kwargs)
    else:
        return response.xpath(selector, **kwargs)
