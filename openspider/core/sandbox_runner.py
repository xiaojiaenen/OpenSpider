"""沙箱执行器 — 统一入口，自动选择子进程或 Docker 沙箱

根据 settings.sandbox_mode 自动切换：
- "subprocess" (默认): 子进程隔离 + 资源限制
- "docker": Docker 容器隔离，每个爬虫一个容器
- "none": 不使用沙箱（仅用于开发调试）

所有爬虫默认走沙箱，爬虫代码无需做任何适配。
"""

from __future__ import annotations

import asyncio
import multiprocessing
import resource
import signal
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from openspider.core.sandbox import validate_source


# ── 配置 ──────────────────────────────────────────────────

@dataclass
class SandboxConfig:
    """沙箱资源限制配置"""

    # 子进程限制
    memory_limit_mb: int = 512
    cpu_time_limit_seconds: int = 120
    file_size_limit_mb: int = 10
    max_open_files: int = 64
    max_processes: int = 64
    timeout_seconds: float = 600
    batch_size: int = 100

    # Docker 沙箱（非空则使用 Docker）
    docker_image: str = ""
    docker_memory_limit: str = "512m"
    docker_cpu_quota: int = 50000
    docker_pids_limit: int = 64
    docker_network: str = "bridge"

    @classmethod
    def from_settings(cls) -> "SandboxConfig":
        """从全局配置创建"""
        from openspider.config import settings
        return cls(
            memory_limit_mb=settings.sandbox_memory_mb,
            cpu_time_limit_seconds=settings.sandbox_cpu_seconds,
            timeout_seconds=settings.sandbox_timeout,
            docker_image=settings.sandbox_docker_image if settings.sandbox_mode == "docker" else "",
        )


# ── 统一入口 ──────────────────────────────────────────────

async def run_sandboxed(
    code_path: str,
    args: dict | None = None,
    config: SandboxConfig | None = None,
) -> AsyncGenerator[dict, None]:
    """在沙箱中运行爬虫，逐条 yield 数据项

    自动根据 config.docker_image 选择：
    - 有 docker_image → Docker 容器沙箱 (Layer 2)
    - 无 docker_image → 子进程沙箱 (Layer 1)

    Args:
        code_path: 爬虫 .py 文件的绝对路径
        args: 运行时参数 {"params": {...}, "user_id": "..."}
        config: 沙箱配置，默认从 settings 创建

    Yields:
        dict: 爬虫产出的每条数据

    Raises:
        SandboxViolationError: AST 预检失败
        TimeoutError: 爬虫执行超时
        RuntimeError: 爬虫运行时错误
    """
    if config is None:
        config = SandboxConfig.from_settings()

    args = args or {}

    # ── Layer 0: AST 预检（两种模式都执行）──
    source = Path(code_path).read_text(encoding="utf-8")
    violations = validate_source(source, code_path)
    if violations:
        raise SandboxViolationError(violations)

    # ── 根据配置选择沙箱层 ──
    if config.docker_image:
        logger.info(f"使用 Docker 沙箱: {config.docker_image}")
        async for item in _run_docker(code_path, args, config):
            yield item
    else:
        logger.debug("使用子进程沙箱")
        async for item in _run_subprocess(code_path, args, config):
            yield item


# ── Layer 1: 子进程沙箱 ──────────────────────────────────

def _child_entry(
    code_path: str,
    args: dict,
    queue: multiprocessing.Queue,
    stop_event: multiprocessing.Event,
    config_dict: dict,
):
    """子进程入口函数"""
    _apply_resource_limits(config_dict)
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    from openspider.core.spider_loader import run_spider_in_subprocess
    try:
        asyncio.run(run_spider_in_subprocess(
            code_path=code_path,
            args=args,
            queue=queue,
            stop_event=stop_event,
            batch_size=config_dict.get("batch_size", 100),
        ))
    except Exception as e:
        try:
            queue.put({"type": "error", "message": f"子进程启动失败: {e}"})
        except Exception:
            pass


def _apply_resource_limits(config: dict):
    """设置 OS 资源限制"""
    limits = [
        (resource.RLIMIT_AS, config["memory_limit_mb"] << 20),
        (resource.RLIMIT_CPU, config["cpu_time_limit_seconds"]),
        (resource.RLIMIT_FSIZE, config["file_size_limit_mb"] << 20),
        (resource.RLIMIT_NOFILE, config["max_open_files"]),
    ]
    try:
        limits.append((resource.RLIMIT_NPROC, config.get("max_processes", 64)))
    except (ValueError, AttributeError):
        pass

    for res, limit in limits:
        try:
            resource.setrlimit(res, (limit, limit))
        except (ValueError, OSError):
            pass

    try:
        import ctypes, ctypes.util
        libc_path = ctypes.util.find_library("c")
        if libc_path:
            libc = ctypes.CDLL(libc_path)
            libc.prctl(38, 1, 0, 0, 0)  # PR_SET_NO_NEW_PRIVS
    except Exception:
        pass


async def _run_subprocess(
    code_path: str,
    args: dict,
    config: SandboxConfig,
) -> AsyncGenerator[dict, None]:
    """子进程沙箱执行"""
    import queue as _queue

    queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=50)
    stop_event: multiprocessing.Event = multiprocessing.Event()

    config_dict = {
        "memory_limit_mb": config.memory_limit_mb,
        "cpu_time_limit_seconds": config.cpu_time_limit_seconds,
        "file_size_limit_mb": config.file_size_limit_mb,
        "max_open_files": config.max_open_files,
        "max_processes": config.max_processes,
        "batch_size": config.batch_size,
    }

    proc = multiprocessing.Process(
        target=_child_entry,
        args=(code_path, args, queue, stop_event, config_dict),
        daemon=True,
    )
    proc.start()

    loop = asyncio.get_running_loop()
    timeout = config.timeout_seconds
    deadline = time.monotonic() + timeout

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.error(f"爬虫执行超时 ({timeout}s)，终止子进程 PID={proc.pid}")
                _kill_process(proc)
                raise TimeoutError(f"爬虫执行超时 ({timeout}s)")

            try:
                msg = await asyncio.wait_for(
                    loop.run_in_executor(None, queue.get, True, min(2.0, remaining)),
                    timeout=remaining + 1,
                )
            except _queue.Empty:
                continue
            except (asyncio.TimeoutError, TimeoutError):
                logger.error(f"爬虫执行超时 ({timeout}s)，终止子进程 PID={proc.pid}")
                _kill_process(proc)
                raise TimeoutError(f"爬虫执行超时 ({timeout}s)")
            except (ValueError, EOFError):
                break

            if msg["type"] == "items":
                for item in msg["data"]:
                    yield item
            elif msg["type"] == "done":
                break
            elif msg["type"] == "error":
                raise RuntimeError(msg["message"])
    finally:
        stop_event.set()
        _kill_process(proc)


def _kill_process(proc: multiprocessing.Process):
    if not proc.is_alive():
        return
    proc.terminate()
    try:
        proc.join(timeout=5)
    except Exception:
        pass
    if proc.is_alive():
        proc.kill()
        try:
            proc.join(timeout=3)
        except Exception:
            pass


# ── Layer 2: Docker 沙箱 ─────────────────────────────────

async def _run_docker(
    code_path: str,
    args: dict,
    config: SandboxConfig,
) -> AsyncGenerator[dict, None]:
    """Docker 容器沙箱执行

    每次执行：
    1. 创建一个临时容器（read_only, cap_drop ALL）
    2. 爬虫代码以只读方式挂载进容器
    3. 容器内运行 runner.py，通过 stdout 输出 JSON 行
    4. 主进程从 stdout 流式读取结果
    5. 执行结束后容器自动删除
    """
    import json

    try:
        import docker
    except ImportError:
        raise RuntimeError(
            "Docker 沙箱需要 docker 库: pip install docker\n"
            "或设置 SANDBOX_MODE=subprocess 使用子进程沙箱"
        )

    client = docker.from_env()
    code_dir = str(Path(code_path).parent)
    code_file = Path(code_path).name
    args_json = json.dumps(args)

    container = None
    try:
        container = client.containers.run(
            config.docker_image,
            command=f"python /runtime/runner.py /code/{code_file} '{args_json}'",
            volumes={code_dir: {"bind": "/code", "mode": "ro"}},
            read_only=True,
            tmpfs={"/tmp": "size=50m"},
            mem_limit=config.docker_memory_limit,
            cpu_quota=config.docker_cpu_quota,
            pids_limit=config.docker_pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            network_mode=config.docker_network,
            detach=True,
            stdout=True,
            stderr=True,
        )

        loop = asyncio.get_running_loop()

        def _read_logs():
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

        try:
            msgs = await asyncio.wait_for(
                loop.run_in_executor(None, _read_logs),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(f"Docker 容器执行超时 ({config.timeout_seconds}s)")
            try:
                container.kill()
            except Exception:
                pass
            raise TimeoutError(f"爬虫执行超时 ({config.timeout_seconds}s)")

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


# ── 异常类 ────────────────────────────────────────────────

class SandboxViolationError(Exception):
    """AST 预检发现违规代码"""

    def __init__(self, violations: list[str]):
        self.violations = violations
        msg = "爬虫代码安全校验失败:\n" + "\n".join(f"  - {v}" for v in violations)
        super().__init__(msg)
