"""爬虫注册表 — 发现、注册、热加载"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

from loguru import logger

from openspider.core.sandbox import validate_source
from openspider.spiders.base import BaseSpider

# 危险模块和函数黑名单
BLOCKED_MODULES = {
    "subprocess", "shlex", "ctypes", "multiprocessing",
    "socket", "http.server", "xmlrpc", "ftplib", "smtplib",
    "telnetlib", "pickle", "shelve", "marshal",
    "code", "codeop", "compile",  # compile is a builtin
    "importlib", "pkgutil",
}

BLOCKED_BUILTINS = {
    "eval", "exec", "compile", "__import__", "globals", "locals",
    "breakpoint", "exit", "quit",
}

BLOCKED_ATTRS = {
    "os.system", "os.popen", "os.exec", "os.spawn",
    "subprocess.Popen", "subprocess.call", "subprocess.run", "subprocess.check_output",
    "shutil.rmtree", "shutil.copytree",
}


class SecurityError(ValueError):
    """安全检查失败"""
    pass


class SpiderRegistry:
    """爬虫注册表

    职责：
    - 启动时扫描 spiders/ 目录，自动导入继承 BaseSpider 的类并注册
    - 运行时支持动态注册（API 上传）
    - 支持文件监控热加载
    """

    def __init__(self, spiders_dir: Path):
        self.spiders_dir = spiders_dir
        self._spiders: dict[str, type[BaseSpider]] = {}   # name -> class
        self._file_map: dict[str, str] = {}                # file_path -> name

    @property
    def spiders(self) -> dict[str, type[BaseSpider]]:
        """返回所有已注册爬虫"""
        return dict(self._spiders)

    def get(self, name: str) -> type[BaseSpider] | None:
        """按名称获取爬虫类"""
        return self._spiders.get(name)

    def get_file_path(self, name: str) -> Path | None:
        """按名称获取爬虫文件路径"""
        for file_path, spider_name in self._file_map.items():
            if spider_name == name:
                return Path(file_path)
        return None

    def list_all(self) -> list[dict]:
        """列出所有爬虫基本信息"""
        result = []
        for name, cls in self._spiders.items():
            result.append({
                "name": name,
                "description": getattr(cls, "description", ""),
                "schedule": getattr(cls, "schedule", None),
                "use_stealth": getattr(cls, "use_stealth", False),
            })
        return result

    def scan_directory(self) -> int:
        """扫描 spiders/ 目录，导入并注册所有爬虫类

        Returns:
            新注册的爬虫数量
        """
        count = 0
        if not self.spiders_dir.exists():
            logger.warning(f"spiders 目录不存在: {self.spiders_dir}")
            return count

        for py_file in self.spiders_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                new_count = self._load_file(py_file)
                count += new_count
            except Exception as e:
                logger.error(f"加载爬虫文件失败 {py_file}: {e}")
        return count

    def register_file(self, file_path: Path) -> list[str]:
        """注册单个爬虫文件，返回注册的爬虫 name 列表

        Raises:
            ValueError: 语法错误或接口不合规
        """
        self._validate_syntax(file_path)
        names = self._load_file(file_path, strict=True)
        return [n for n in self._file_map.values() if self._file_map.get(str(file_path)) == n]

    def _validate_syntax(self, file_path: Path) -> None:
        """校验 Python 文件语法 + 安全检查"""
        source = file_path.read_text(encoding="utf-8")
        try:
            compile(source, str(file_path), "exec")
        except SyntaxError as e:
            raise ValueError(f"语法错误: {e}") from e
        self._check_security(source, str(file_path))

    def _check_security(self, source: str, filename: str = "<string>") -> None:
        """AST 静态分析，拦截危险代码模式"""
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError:
            return  # 语法错误已在上一步处理

        for node in ast.walk(tree):
            # 检查 import 语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod in BLOCKED_MODULES:
                        raise SecurityError(
                            f"禁止导入模块: {alias.name} (第 {node.lineno} 行)"
                        )

            # 检查 from ... import 语句
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]
                    if mod in BLOCKED_MODULES:
                        raise SecurityError(
                            f"禁止导入模块: {node.module} (第 {node.lineno} 行)"
                        )

            # 检查函数调用
            elif isinstance(node, ast.Call):
                # eval(), exec(), __import__() 等
                if isinstance(node.func, ast.Name):
                    if node.func.id in BLOCKED_BUILTINS:
                        raise SecurityError(
                            f"禁止调用: {node.func.id}() (第 {node.lineno} 行)"
                        )

                # os.system(), subprocess.run() 等
                if isinstance(node.func, ast.Attribute):
                    parts = []
                    obj = node.func
                    while isinstance(obj, ast.Attribute):
                        parts.append(obj.attr)
                        obj = obj.value
                    if isinstance(obj, ast.Name):
                        parts.append(obj.id)
                    call_path = ".".join(reversed(parts))
                    for blocked in BLOCKED_ATTRS:
                        if call_path.startswith(blocked):
                            raise SecurityError(
                                f"禁止调用: {call_path}() (第 {node.lineno} 行)"
                            )

            # 检查 __builtins__ 访问
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
                    raise SecurityError(
                        f"禁止访问 __builtins__ (第 {node.lineno} 行)"
                    )

    def _load_file(self, file_path: Path, strict: bool = False) -> int:
        """从文件加载爬虫类

        Args:
            file_path: Python 文件路径
            strict: True 时接口不合规抛异常，False 时静默跳过

        Returns:
            新注册的爬虫数量
        """
        source = file_path.read_text(encoding="utf-8")

        # 语法检查
        try:
            compile(source, str(file_path), "exec")
        except SyntaxError as e:
            if strict:
                raise ValueError(f"语法错误: {e}") from e
            logger.warning(f"语法错误，跳过 {file_path}: {e}")
            return 0

        # AST 安全预检（Layer 0）
        violations = validate_source(source, str(file_path))
        if violations:
            msg = f"安全校验失败 ({file_path}):\n" + "\n".join(f"  - {v}" for v in violations)
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return 0

        # 动态导入
        module_name = f"_spider_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            return 0
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            if strict:
                raise ValueError(f"导入失败: {e}") from e
            logger.warning(f"导入失败，跳过 {file_path}: {e}")
            return 0

        # 查找继承 BaseSpider 的类
        count = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSpider)
                and attr is not BaseSpider
                and not attr_name.startswith("_")
            ):
                spider_name = getattr(attr, "name", "") or attr_name
                # 覆盖已有的同名爬虫（更新场景）
                if spider_name in self._spiders:
                    logger.info(f"覆盖已有爬虫: {spider_name}")
                    # 清理旧的 file_map 条目
                    old_keys = [k for k, v in self._file_map.items() if v == spider_name]
                    for k in old_keys:
                        del self._file_map[k]
                self._spiders[spider_name] = attr
                self._file_map[str(file_path)] = spider_name
                logger.info(f"注册爬虫: {spider_name} ({file_path})")
                count += 1
        return count

    def unregister(self, name: str) -> bool:
        """注销爬虫

        Returns:
            是否成功注销
        """
        if name in self._spiders:
            del self._spiders[name]
            # 清理 file_map
            to_remove = [k for k, v in self._file_map.items() if v == name]
            for k in to_remove:
                del self._file_map[k]
            logger.info(f"注销爬虫: {name}")
            return True
        return False
