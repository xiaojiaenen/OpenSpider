"""Compat 缃戠珯鍏煎灞傛祴璇?""

import pytest
from openspider.utils.encoding import detect_encoding, extract_meta_charset, _normalize_encoding
from openspider.utils.url import strip_jsessionid, normalize_url, resolve_url
from openspider.utils.form import extract_hidden_fields, merge_form_data, extract_asp_viewstate


# === 缂栫爜妫�娴?===

def test_detect_encoding_with_declared():
    """鎵嬪姩鎸囧畾缂栫爜"""
    assert detect_encoding(b"hello", "gbk") == "gbk"


def test_detect_encoding_utf8():
    """UTF-8 鍐呭"""
    result = detect_encoding("浣犲ソ".encode("utf-8"))
    assert result.lower().replace("-", "") in ("utf8", "utf_8", "utf-8")


def test_extract_meta_charset():
    """浠?meta 鏍囩鎻愬彇缂栫爜"""
    html = b'<html><head><meta charset="gbk"></head></html>'
    assert extract_meta_charset(html) == "gbk"


def test_extract_meta_charset_http_equiv():
    """浠?http-equiv 鎻愬彇缂栫爜"""
    html = b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=big5"></head></html>'
    assert extract_meta_charset(html) == "big5"


def test_extract_meta_charset_none():
    """鏃犵紪鐮佸０鏄?""
    assert extract_meta_charset(b"<html><head></head></html>") is None


def test_normalize_encoding():
    """缂栫爜鍚嶇О鏍囧噯鍖?""
    assert _normalize_encoding("gb2312") == "gbk"
    assert _normalize_encoding("utf-8") == "utf-8"
    assert _normalize_encoding("latin1") == "latin-1"


# === URL 澶勭悊 ===

def test_strip_jsessionid():
    """鍓ョ jsessionid"""
    url, sid = strip_jsessionid("/page.jsp;jsessionid=ABC123")
    assert url == "/page.jsp"
    assert sid == "ABC123"


def test_strip_jsessionid_none():
    """鏃?jsessionid"""
    url, sid = strip_jsessionid("/page.jsp")
    assert url == "/page.jsp"
    assert sid is None


def test_resolve_url():
    """鐩稿 URL 鎷兼帴"""
    assert resolve_url("https://example.com/page/", "../other") == "https://example.com/other"


def test_normalize_url():
    """URL 瑙勮寖鍖?""
    result = normalize_url("https://example.com/path?b=2&a=1")
    assert "a=1" in result
    assert "b=2" in result


# === 琛ㄥ崟澶勭悊 ===

class MockSelectors:
    """妯℃嫙 Scrapling Selectors"""
    def __init__(self, items=None):
        self._items = items or []

    def css(self, selector):
        return MockSelectors([])

    def __bool__(self):
        return bool(self._items)

    def __iter__(self):
        return iter(self._items)


class MockElement:
    """妯℃嫙 Scrapling Element"""
    def __init__(self, attrib=None, text=""):
        self.attrib = attrib or {}
        self.text = text


def test_merge_form_data():
    """鍚堝苟琛ㄥ崟鏁版嵁"""
    hidden = {"__VIEWSTATE": "abc", "token": "123"}
    user = {"username": "admin", "password": "pass"}
    result = merge_form_data(hidden, user)
    assert result["__VIEWSTATE"] == "abc"
    assert result["username"] == "admin"
    assert result["password"] == "pass"


def test_merge_form_data_override():
    """鐢ㄦ埛鏁版嵁瑕嗙洊闅愯棌瀛楁"""
    hidden = {"field": "old"}
    user = {"field": "new"}
    result = merge_form_data(hidden, user)
    assert result["field"] == "new"


