"""爬虫注册表 — 发现、注册、热加载"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from loguru import logger

from openspider.spiders.base import BaseSpider


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
        """校验 Python 文件语法"""
        source = file_path.read_text(encoding="utf-8")
        try:
            compile(source, str(file_path), "exec")
        except SyntaxError as e:
            raise ValueError(f"语法错误: {e}") from e

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
                # name 唯一性检查
                if spider_name in self._spiders and strict:
                    raise ValueError(f"爬虫 name '{spider_name}' 已存在")
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
