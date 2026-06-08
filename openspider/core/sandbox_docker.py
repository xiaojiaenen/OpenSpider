"""Layer 2: Docker 容器沙箱 — 最强隔离，用于不可信代码

每个爬虫运行在独立的 Docker 容器中：
- 文件系统隔离 (read_only + tmpfs)
- 能力限制 (cap_drop ALL, no-new-privileges)
- 资源限制 (memory, cpu, pids)
- 网络可选 (bridge/none)

使用前需要：
1. 安装 docker: pip install docker
2. 构建运行时镜像: docker build -f Dockerfile.runtime -t openspider-runtime .
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from openspider.core.sandbox import validate_source


@dataclass
class DockerSandboxConfig:
    """Docker 沙箱配置"""

    image: str = "openspider-runtime:latest"
    memory_limit: str = "512m"
    cpu_quota: int = 50000               # 50% of one CPU (100000 = 100%)
    pids_limit: int = 64
    tmpfs_size: str = "50m"
    network_mode: str = "bridge"          # "none" = 禁网
    timeout_seconds: float = 300
    batch_size: int = 100


DEFAULT_DOCKER_CONFIG = DockerSandboxConfig()


async def run_sandboxed_docker(
    code_path: str,
    args: dict | None = None,
    config: DockerSandboxConfig | None = None,
) -> AsyncGenerator[dict, None]:
    """在 Docker 容器中运行爬虫，逐条 yield 数据项

    Args:
        code_path: 爬虫 .py 文件的绝对路径
        args: 运行时参数
        config: Docker 沙箱配置

    Yields:
        dict: 爬虫产出的每条数据
    """
    cfg = config or DEFAULT_DOCKER_CONFIG
    args = args or {}

    # ── Layer 0: AST 预检 ──
    source = Path(code_path).read_text(encoding="utf-8")
    violations = validate_source(source, code_path)
    if violations:
        from openspider.core.sandbox_runner import SandboxViolationError
        raise SandboxViolationError(violations)

    # ── Layer 2: Docker 容器执行 ──
    try:
        import docker
    except ImportError:
        raise RuntimeError(
            "Docker 沙箱需要 docker 库: pip install docker\n"
            "或使用子进程沙箱（不设置 docker_image）"
        )

    client = docker.from_env()
    code_dir = str(Path(code_path).parent)
    code_file = Path(code_path).name
    args_json = json.dumps(args)

    container = None
    try:
        container = client.containers.run(
            cfg.image,
            command=f"python /runtime/runner.py /code/{code_file} '{args_json}'",
            volumes={
                code_dir: {"bind": "/code", "mode": "ro"},
            },
            # ── 安全限制 ──
            read_only=True,
            tmpfs={"/tmp": f"size={cfg.tmpfs_size}"},
            mem_limit=cfg.memory_limit,
            cpu_quota=cfg.cpu_quota,
            pids_limit=cfg.pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            network_mode=cfg.network_mode,
            detach=True,
            stdout=True,
            stderr=True,
        )

        # 从容器 stdout 流式读取结果
        loop = asyncio.get_running_loop()

        def _read_logs():
            """同步读取容器日志（在线程中执行）"""
            msgs = []
            try:
                for chunk in container.logs(stream=True, follow=True):
                    line = chunk.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        msgs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except Exception:
                pass
            return msgs

        # 用超时保护
        try:
            msgs = await asyncio.wait_for(
                loop.run_in_executor(None, _read_logs),
                timeout=cfg.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(f"Docker 容器执行超时 ({cfg.timeout_seconds}s)")
            try:
                container.kill()
            except Exception:
                pass
            raise TimeoutError(f"爬虫执行超时 ({cfg.timeout_seconds}s)")

        for msg in msgs:
            if msg.get("type") == "item":
                yield msg["data"]
            elif msg.get("type") == "error":
                raise RuntimeError(msg.get("message", "容器内未知错误"))

    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass


# ── 容器内 runner 脚本 ───────────────────────────────────

CONTAINER_RUNNER_SCRIPT = '''\
#!/usr/bin/env python3
"""容器内爬虫执行器 — 从文件加载爬虫，运行，将结果输出为 JSON 行"""

import asyncio
import importlib.util
import json
import sys


async def main():
    code_path = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    # 加载爬虫模块
    spec = importlib.util.spec_from_file_location("spider_mod", code_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 找 BaseSpider 子类
    from openspider.spiders.base import BaseSpider
    spider_cls = None
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, BaseSpider) and obj is not BaseSpider:
            spider_cls = obj
            break

    if spider_cls is None:
        print(json.dumps({"type": "error", "message": "未找到 BaseSpider 子类"}))
        sys.exit(1)

    spider = spider_cls()
    spider.params = args.get("params", {})

    try:
        async for item in spider.run():
            if isinstance(item, dict):
                processed = await spider.on_item_scraped(item)
                if processed is not None:
                    print(json.dumps({"type": "item", "data": processed}), flush=True)
        print(json.dumps({"type": "done"}), flush=True)
    except Exception as e:
        print(json.dumps({"type": "error", "message": str(e)}), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
'''
