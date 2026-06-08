"""Scrapling Spider 动态创建工具 — 统一配置转发逻辑

Runner 和模板爬虫（RuleSpider/SitemapRuleSpider）都需要
从 BaseSpider 配置动态创建 Scrapling Spider 子类，转发全部配置。
此模块抽取公共逻辑，避免重复代码。
"""

from __future__ import annotations

import os
from pathlib import Path

from scrapling.spiders import Spider
from scrapling.fetchers import FetcherSession, AsyncStealthySession, ProxyRotator

from openspider.spiders.base import BaseSpider


def _is_docker() -> bool:
    """检测是否运行在 Docker 容器内"""
    return Path("/.dockerenv").exists() or os.environ.get("DOCKER_CONTAINER") == "1"


def build_session_kwargs(spider: BaseSpider) -> dict:
    """从 BaseSpider 构建 FetcherSession 参数"""
    kwargs = {
        "impersonate": spider.impersonate,
        "http3": spider.http3,
        "stealthy_headers": spider.stealthy_headers,
        "verify": spider.ssl_verify,
        "timeout": spider.timeout,
    }
    if spider.default_headers:
        kwargs["headers"] = spider.default_headers
    if spider.cookies:
        kwargs["cookies"] = spider.cookies
    if spider.follow_redirects is False:
        kwargs["follow_redirects"] = False
    elif spider.allow_internal_redirects:
        kwargs["follow_redirects"] = True
    return kwargs


def build_stealth_kwargs(spider: BaseSpider) -> dict:
    """从 BaseSpider 构建 AsyncStealthySession 参数"""
    kwargs = {
        "headless": True,
        "solve_cloudflare": spider.solve_cloudflare,
        "block_webrtc": spider.block_webrtc,
        "hide_canvas": spider.hide_canvas,
        "allow_webgl": spider.allow_webgl,
        "real_chrome": spider.real_chrome,
        "cdp_url": spider.cdp_url,
        "user_data_dir": spider.user_data_dir,
        "max_pages": spider.max_pages,
        "block_ads": spider.block_ads,
        "dns_over_https": spider.dns_over_https,
        "locale": spider.locale,
        "timezone_id": spider.timezone_id,
        "wait": spider.wait,
        "disable_resources": spider.disable_resources,
        "network_idle": spider.network_idle,
        "load_dom": spider.load_dom,
        "wait_selector": spider.wait_selector,
        "wait_selector_state": spider.wait_selector_state,
        "init_script": spider.init_script,
        "capture_xhr": spider.capture_xhr,
    }
    # Docker 容器内 Chromium 需要 --no-sandbox
    if _is_docker():
        kwargs["extra_flags"] = ["--no-sandbox"]
    # 页面交互钩子（浏览器自动化场景）
    if spider.page_action and callable(spider.page_action):
        kwargs["page_action"] = spider.page_action
    if spider.page_setup and callable(spider.page_setup):
        kwargs["page_setup"] = spider.page_setup
    return kwargs


def inject_proxy(spider: BaseSpider, session_kwargs: dict, stealth_kwargs: dict):
    """将代理配置注入 session_kwargs / stealth_kwargs

    多个代理自动使用 ProxyRotator 轮换。
    """
    if not spider.proxies:
        return

    if len(spider.proxies) > 1:
        rotator = ProxyRotator(spider.proxies)
        if spider.use_stealth:
            stealth_kwargs["proxy_rotator"] = rotator
        else:
            session_kwargs["proxy_rotator"] = rotator
    else:
        session_kwargs["proxy"] = spider.proxies[0]


def configure_session(manager, spider: BaseSpider):
    """为 Scrapling Spider 的 configure_sessions 注入 session

    根据 use_stealth 选择 FetcherSession 或 AsyncStealthySession。
    """
    session_kwargs = build_session_kwargs(spider)
    stealth_kwargs = build_stealth_kwargs(spider)
    inject_proxy(spider, session_kwargs, stealth_kwargs)

    if spider.use_stealth:
        manager.add("default", AsyncStealthySession(**stealth_kwargs))
    else:
        manager.add("default", FetcherSession(**session_kwargs))


def create_scrapling_spider(spider: BaseSpider, parse_callback=None):
    """从 BaseSpider 动态创建 Scrapling Spider 子类

    Args:
        spider: BaseSpider 实例
        parse_callback: 可选的自定义 parse 方法。默认使用 spider.parse()

    Returns:
        Scrapling Spider 子类
    """
    _has_custom_parse = type(spider).parse is not BaseSpider.parse

    class DynamicSpider(Spider):
        name = spider.name
        start_urls = spider.start_urls
        concurrent_requests = spider.concurrent_requests
        download_delay = spider.download_delay
        robots_txt_obey = spider.robots_txt_obey
        development_mode = spider.development_mode

        def configure_sessions(self_inner, manager):
            configure_session(manager, spider)

        async def parse(self_inner, response):
            if parse_callback is not None:
                async for result in parse_callback(response):
                    yield result
            elif _has_custom_parse:
                async for result in spider.parse(response):
                    yield result
            else:
                spider._scrapling_response = response
                spider._session = self_inner._session
                async for result in spider.run():
                    yield result

    return DynamicSpider
