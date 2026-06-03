"""Compat 网站兼容层测试"""

import pytest
from openspider.utils.encoding import detect_encoding, extract_meta_charset, _normalize_encoding
from openspider.utils.url import strip_jsessionid, normalize_url, resolve_url
from openspider.utils.form import extract_hidden_fields, merge_form_data, extract_asp_viewstate


# === 编码检测 ===

def test_detect_encoding_with_declared():
    """手动指定编码"""
    assert detect_encoding(b"hello", "gbk") == "gbk"


def test_detect_encoding_utf8():
    """UTF-8 内容"""
    result = detect_encoding("你好".encode("utf-8"))
    assert result.lower().replace("-", "") in ("utf8", "utf_8", "utf-8")


def test_extract_meta_charset():
    """从 meta 标签提取编码"""
    html = b'<html><head><meta charset="gbk"></head></html>'
    assert extract_meta_charset(html) == "gbk"


def test_extract_meta_charset_http_equiv():
    """从 http-equiv 提取编码"""
    html = b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=big5"></head></html>'
    assert extract_meta_charset(html) == "big5"


def test_extract_meta_charset_none():
    """无编码声明"""
    assert extract_meta_charset(b"<html><head></head></html>") is None


def test_normalize_encoding():
    """编码名称标准化"""
    assert _normalize_encoding("gb2312") == "gbk"
    assert _normalize_encoding("utf-8") == "utf-8"
    assert _normalize_encoding("latin1") == "latin-1"


# === URL 处理 ===

def test_strip_jsessionid():
    """剥离 jsessionid"""
    url, sid = strip_jsessionid("/page.jsp;jsessionid=ABC123")
    assert url == "/page.jsp"
    assert sid == "ABC123"


def test_strip_jsessionid_none():
    """无 jsessionid"""
    url, sid = strip_jsessionid("/page.jsp")
    assert url == "/page.jsp"
    assert sid is None


def test_resolve_url():
    """相对 URL 拼接"""
    assert resolve_url("https://example.com/page/", "../other") == "https://example.com/other"


def test_normalize_url():
    """URL 规范化"""
    result = normalize_url("https://example.com/path?b=2&a=1")
    assert "a=1" in result
    assert "b=2" in result


# === 表单处理 ===

class MockSelectors:
    """模拟 Scrapling Selectors"""
    def __init__(self, items=None):
        self._items = items or []

    def css(self, selector):
        return MockSelectors([])

    def __bool__(self):
        return bool(self._items)

    def __iter__(self):
        return iter(self._items)


class MockElement:
    """模拟 Scrapling Element"""
    def __init__(self, attrib=None, text=""):
        self.attrib = attrib or {}
        self.text = text


def test_merge_form_data():
    """合并表单数据"""
    hidden = {"__VIEWSTATE": "abc", "token": "123"}
    user = {"username": "admin", "password": "pass"}
    result = merge_form_data(hidden, user)
    assert result["__VIEWSTATE"] == "abc"
    assert result["username"] == "admin"
    assert result["password"] == "pass"


def test_merge_form_data_override():
    """用户数据覆盖隐藏字段"""
    hidden = {"field": "old"}
    user = {"field": "new"}
    result = merge_form_data(hidden, user)
    assert result["field"] == "new"
