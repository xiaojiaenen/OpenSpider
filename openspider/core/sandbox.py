"""Layer 0: AST 预检 — 静态分析爬虫代码，拦截明显的恶意操作

不是安全防线（可以被绕过），作用是：
1. 快速失败，给开发者清晰的报错信息
2. 过滤掉 90% 的低级攻击尝试
3. 在子进程启动前就拒绝，节省资源
"""

from __future__ import annotations

import ast
from pathlib import Path

from loguru import logger

# ── 配置 ──────────────────────────────────────────────────

BLOCKED_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "ctypes",
    "importlib", "signal", "multiprocessing", "pty", "pickle",
    "shelve", "dbm", "code", "codeop", "compileall",
    "webbrowser", "platform", "pdb", "profile", "cProfile",
    "trace", "traceback", "inspect", "gc", "faulthandler",
})

BLOCKED_BUILTINS_CALL = frozenset({
    "eval", "exec", "compile", "__import__", "globals",
    "locals", "vars", "breakpoint", "exit", "quit",
})

BLOCKED_ATTRS = frozenset({
    "__subclasses__", "__bases__", "__mro__", "__globals__",
    "__code__", "__class__", "__builtins__", "__loader__",
    "__spec__", "__import__", "system", "popen",
})

# ── AST 访问器 ────────────────────────────────────────────


class _ASTValidator(ast.NodeVisitor):
    """AST 静态分析器，收集违规信息"""

    def __init__(self):
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in BLOCKED_MODULES:
                self.errors.append(f"第{node.lineno}行: 禁止 import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module is None:
            self.generic_visit(node)
            return
        # 通配符导入
        if any(a.name == "*" for a in node.names):
            self.errors.append(f"第{node.lineno}行: 禁止 from {node.module} import *")
        root = node.module.split(".")[0]
        if root in BLOCKED_MODULES:
            self.errors.append(f"第{node.lineno}行: 禁止 from {node.module} import ...")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS_CALL:
            self.errors.append(f"第{node.lineno}行: 禁止调用 {node.func.id}()")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in BLOCKED_ATTRS:
            self.errors.append(f"第{node.lineno}行: 禁止访问 .{node.attr}")
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete):
        self.errors.append(f"第{node.lineno}行: 禁止 del 语句")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global):
        self.errors.append(f"第{node.lineno}行: 禁止 global 语句")
        self.generic_visit(node)


# ── 对外接口 ──────────────────────────────────────────────


def validate_source(source: str, file_path: str = "<spider>") -> list[str]:
    """校验爬虫源码，返回违规列表

    Args:
        source: Python 源码字符串
        file_path: 文件路径（仅用于报错信息）

    Returns:
        违规信息列表，空列表表示通过
    """
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return [f"语法错误: {e}"]

    validator = _ASTValidator()
    validator.visit(tree)
    return validator.errors


def validate_file(file_path: str | Path) -> list[str]:
    """校验爬虫文件，返回违规列表"""
    path = Path(file_path) if isinstance(file_path, str) else file_path
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"读取文件失败: {e}"]
    return validate_source(source, str(path))
