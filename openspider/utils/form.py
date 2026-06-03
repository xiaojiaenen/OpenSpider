"""HTML 表单字段提取、隐藏字段收集"""

from __future__ import annotations

import re


def extract_form_fields(response, form_selector: str = "form") -> dict:
    """提取表单中所有字段的默认值

    Args:
        response: Scrapling Response 对象
        form_selector: 表单 CSS 选择器

    Returns:
        字段名 -> 默认值 的字典
    """
    form = response.css(form_selector)
    if not form:
        return {}

    fields = {}

    # input 字段
    for inp in form.css("input"):
        name = inp.attrib.get("name", "")
        if not name:
            continue
        input_type = inp.attrib.get("type", "text").lower()

        if input_type in ("hidden", "text", "password", "email", "number", "tel", "url"):
            fields[name] = inp.attrib.get("value", "")
        elif input_type == "checkbox":
            if inp.attrib.get("checked") is not None:
                fields[name] = inp.attrib.get("value", "on")
        elif input_type == "radio":
            if inp.attrib.get("checked") is not None:
                fields[name] = inp.attrib.get("value", "")
        elif input_type == "submit":
            fields[name] = inp.attrib.get("value", "")

    # textarea 字段
    for textarea in form.css("textarea"):
        name = textarea.attrib.get("name", "")
        if name:
            fields[name] = textarea.text or ""

    # select 字段
    for select in form.css("select"):
        name = select.attrib.get("name", "")
        if not name:
            continue
        selected = select.css("option[selected]")
        if selected:
            fields[name] = selected[0].attrib.get("value", "")
        else:
            first_option = select.css("option")
            if first_option:
                fields[name] = first_option[0].attrib.get("value", "")

    return fields


def extract_hidden_fields(response, form_selector: str = "form") -> dict:
    """提取表单中所有隐藏字段

    ASP.NET ViewState、CSRF token 等都在这里。

    Args:
        response: Scrapling Response 对象
        form_selector: 表单 CSS 选择器

    Returns:
        隐藏字段名 -> 值 的字典
    """
    form = response.css(form_selector)
    if not form:
        return {}

    fields = {}
    for inp in form.css("input[type='hidden']"):
        name = inp.attrib.get("name", "")
        if name:
            fields[name] = inp.attrib.get("value", "")

    return fields


def merge_form_data(hidden_fields: dict, user_data: dict) -> dict:
    """合并隐藏字段与用户数据

    Args:
        hidden_fields: 隐藏字段（ViewState 等）
        user_data: 用户传入的数据

    Returns:
        合并后的完整 form data dict，用户数据优先
    """
    merged = dict(hidden_fields)
    merged.update(user_data)
    return merged


def extract_asp_viewstate(response, form_selector: str = "form") -> dict:
    """提取 ASP.NET WebForms 的特殊隐藏字段

    Args:
        response: Scrapling Response 对象
        form_selector: 表单 CSS 选择器

    Returns:
        ASP.NET 特殊字段字典
    """
    hidden = extract_hidden_fields(response, form_selector)
    asp_fields = {}
    for key in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                "__EVENTTARGET", "__EVENTARGUMENT", "__PREVIOUSPAGE"):
        if key in hidden:
            asp_fields[key] = hidden[key]
    return asp_fields
