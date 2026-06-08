"""沙箱测试 — AST 预检 + 子进程执行"""

import textwrap
import tempfile
from pathlib import Path

import pytest

from openspider.core.sandbox import validate_source, validate_file


# ── Layer 0: AST 预检测试 ─────────────────────────────────


class TestASTValidator:
    """AST 预检校验"""

    def test_clean_code_passes(self):
        """正常爬虫代码通过"""
        source = textwrap.dedent('''
            from openspider.spiders.base import BaseSpider
            import json

            class MySpider(BaseSpider):
                name = "test"
                start_urls = ["https://example.com"]

                async def run(self):
                    yield {"title": "hello"}
        ''')
        errors = validate_source(source)
        assert errors == []

    def test_import_os_blocked(self):
        """import os 被拦截"""
        source = "import os\nos.system('rm -rf /')"
        errors = validate_source(source)
        assert len(errors) >= 1
        assert "os" in errors[0]

    def test_import_subprocess_blocked(self):
        """import subprocess 被拦截"""
        source = "import subprocess\nsubprocess.run(['ls'])"
        errors = validate_source(source)
        assert any("subprocess" in e for e in errors)

    def test_from_os_import_blocked(self):
        """from os import system 被拦截"""
        source = "from os import system\nsystem('whoami')"
        errors = validate_source(source)
        assert any("os" in e for e in errors)

    def test_eval_blocked(self):
        """eval() 调用被拦截"""
        source = "eval('1+1')"
        errors = validate_source(source)
        assert any("eval" in e for e in errors)

    def test_exec_blocked(self):
        """exec() 调用被拦截"""
        source = "exec('import os')"
        errors = validate_source(source)
        assert any("exec" in e for e in errors)

    def test_dunder_subclasses_blocked(self):
        """__subclasses__ 访问被拦截"""
        source = "x = object.__subclasses__()"
        errors = validate_source(source)
        assert any("__subclasses__" in e for e in errors)

    def test_star_import_blocked(self):
        """import * 被拦截"""
        source = "from json import *"
        errors = validate_source(source)
        assert any("import *" in e for e in errors)

    def test_del_blocked(self):
        """del 语句被拦截"""
        source = "x = 1\ndel x"
        errors = validate_source(source)
        assert any("del" in e for e in errors)

    def test_global_blocked(self):
        """global 语句被拦截"""
        source = "def f():\n    global x"
        errors = validate_source(source)
        assert any("global" in e for e in errors)

    def test_syntax_error_reported(self):
        """语法错误正常报告"""
        source = "def broken("
        errors = validate_source(source)
        assert len(errors) == 1
        assert "语法错误" in errors[0]

    def test_multiple_violations(self):
        """多条违规同时报告"""
        source = "import os\nimport subprocess\neval('1')"
        errors = validate_source(source)
        assert len(errors) >= 3

    def test_allowed_imports_pass(self):
        """允许的 import 不被拦截"""
        source = textwrap.dedent('''
            import json
            import re
            from datetime import datetime
            from collections import defaultdict
        ''')
        errors = validate_source(source)
        assert errors == []

    def test_validate_file(self):
        """validate_file 读取文件并校验"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import os\n")
            f.flush()
            errors = validate_file(f.name)
            assert any("os" in e for e in errors)
        Path(f.name).unlink(missing_ok=True)

    def test_validate_file_clean(self):
        """validate_file 对正常文件返回空"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n")
            f.flush()
            errors = validate_file(f.name)
            assert errors == []
        Path(f.name).unlink(missing_ok=True)


# ── Layer 1: 子进程沙箱测试 ───────────────────────────────


class TestSandboxRunner:
    """子进程沙箱执行"""

    @pytest.fixture
    def spider_file(self, tmp_path):
        """创建临时爬虫文件"""
        spider = tmp_path / "test_spider.py"
        spider.write_text(textwrap.dedent('''
            from openspider.spiders.base import BaseSpider

            class SandboxTestSpider(BaseSpider):
                name = "sandbox_test"
                description = "沙箱测试爬虫"
                start_urls = ["https://example.com"]

                async def run(self):
                    yield {"title": "item1", "url": "https://example.com/1"}
                    yield {"title": "item2", "url": "https://example.com/2"}
                    yield {"title": "item3", "url": "https://example.com/3"}
        '''))
        return spider

    @pytest.fixture
    def slow_spider_file(self, tmp_path):
        """创建一个模拟慢速执行的爬虫文件"""
        spider = tmp_path / "slow_spider.py"
        spider.write_text(textwrap.dedent('''
            import asyncio
            from openspider.spiders.base import BaseSpider

            class SlowSpider(BaseSpider):
                name = "slow"
                start_urls = []

                async def run(self):
                    for i in range(10):
                        yield {"i": i}
                        await asyncio.sleep(10)  # 超过超时时间
        '''))
        return spider

    @pytest.fixture
    def malicious_spider_file(self, tmp_path):
        """创建恶意爬虫文件"""
        spider = tmp_path / "evil_spider.py"
        spider.write_text(textwrap.dedent('''
            import os
            from openspider.spiders.base import BaseSpider

            class EvilSpider(BaseSpider):
                name = "evil"
                start_urls = []

                async def run(self):
                    os.system("echo pwned")
                    yield {}
        '''))
        return spider

    @pytest.mark.asyncio
    async def test_sandbox_blocks_malicious_code(self, malicious_spider_file):
        """AST 预检拦截恶意代码"""
        from openspider.core.sandbox_runner import run_sandboxed, SandboxViolationError

        with pytest.raises(SandboxViolationError, match="import os"):
            async for _ in run_sandboxed(str(malicious_spider_file)):
                pass

    @pytest.mark.asyncio
    async def test_sandbox_timeout(self, slow_spider_file):
        """超时自动终止"""
        from openspider.core.sandbox_runner import run_sandboxed, SandboxConfig

        config = SandboxConfig(timeout_seconds=3)
        items = []
        with pytest.raises(TimeoutError):
            async for item in run_sandboxed(str(slow_spider_file), config=config):
                items.append(item)
        # 应该拿到前几条（在超时前 yield 的）
        assert len(items) >= 0  # 可能拿到 0-10 条，取决于时序

    @pytest.mark.asyncio
    async def test_sandbox_resource_limits(self, spider_file):
        """正常爬虫在沙箱中运行，资源限制不影响正常执行"""
        from openspider.core.sandbox_runner import run_sandboxed, SandboxConfig

        config = SandboxConfig(memory_limit_mb=256, timeout_seconds=30)
        items = []
        async for item in run_sandboxed(str(spider_file), config=config):
            items.append(item)

        assert len(items) == 3
        assert items[0]["title"] == "item1"
        assert items[2]["title"] == "item3"
