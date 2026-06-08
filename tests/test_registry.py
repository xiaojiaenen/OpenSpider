"""Registry 注册表测�?""

import pytest
from pathlib import Path
from openspider.core.registry import SpiderRegistry
from openspider.spiders.base import BaseSpider


@pytest.fixture
def registry(tmp_path):
    """创建临时注册�?""
    return SpiderRegistry(tmp_path)


@pytest.fixture
def sample_spider_file(tmp_path):
    """创建示例爬虫文件"""
    spider_dir = tmp_path / "spiders"
    spider_dir.mkdir()
    spider_file = spider_dir / "test_spider.py"
    spider_file.write_text('''
from openspider.spiders.base import BaseSpider

class TestSpider(BaseSpider):
    name = "test"
    description = "test spider"
    start_urls = ["https://example.com"]

    async def run(self):
        yield {"title": "test"}
''')
    return spider_file


def test_registry_init(registry):
    """注册表初始化"""
    assert registry.spiders == {}
    assert registry.list_all() == []


def test_registry_scan(registry, sample_spider_file):
    """扫描目录注册爬虫"""
    count = registry.scan_directory()
    assert count == 1
    assert "test" in registry.spiders


def test_registry_get(registry, sample_spider_file):
    """按名称获取爬�?""
    registry.scan_directory()
    cls = registry.get("test")
    assert cls is not None
    assert cls.name == "test"


def test_registry_get_not_found(registry):
    """获取不存在的爬虫"""
    assert registry.get("nonexistent") is None


def test_registry_list_all(registry, sample_spider_file):
    """列出所有爬�?""
    registry.scan_directory()
    result = registry.list_all()
    assert len(result) == 1
    assert result[0]["name"] == "test"


def test_registry_unregister(registry, sample_spider_file):
    """注销爬虫"""
    registry.scan_directory()
    assert registry.unregister("test") is True
    assert "test" not in registry.spiders
    assert registry.unregister("test") is False


def test_registry_invalid_syntax(tmp_path):
    """语法错误的文�?""
    spider_dir = tmp_path / "spiders"
    spider_dir.mkdir()
    bad_file = spider_dir / "bad.py"
    bad_file.write_text("def broken(")

    registry = SpiderRegistry(tmp_path)
    count = registry.scan_directory()
    assert count == 0


def test_registry_not_base_spider(tmp_path):
    """不继�?BaseSpider 的类"""
    spider_dir = tmp_path / "spiders"
    spider_dir.mkdir()
    bad_file = spider_dir / "bad.py"
    bad_file.write_text('''
class NotASpider:
    name = "bad"
''')

    registry = SpiderRegistry(tmp_path)
    count = registry.scan_directory()
    assert count == 0


def test_registry_validate_syntax(registry, sample_spider_file):
    """语法校验通过"""
    registry._validate_syntax(sample_spider_file)  # 不抛异常


def test_registry_validate_syntax_fail(registry, tmp_path):
    """语法校验失败"""
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def broken(")
    with pytest.raises(ValueError, match="语法错误"):
        registry._validate_syntax(bad_file)


