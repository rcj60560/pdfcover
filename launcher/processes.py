"""拉起/停止工具进程；内存登记（本地工具箱够用）。"""
from __future__ import annotations

import os
import signal
import subprocess

from .probe import port_open


class ProcessRegistry:
    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen] = {}

    def start(self, slug: str, cmd: list[str], cwd, port: int | None = None) -> int:
        self.stop(slug)
        kwargs: dict = {"cwd": str(cwd)}
        if os.name == "nt":
            # 新进程组，便于整组发 CTRL_BREAK 停止
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self._procs[slug] = subprocess.Popen(cmd, **kwargs)
        return self._procs[slug].pid

    def is_running(self, slug: str, port: int | None = None) -> bool:
        proc = self._procs.get(slug)
        alive = bool(proc and proc.poll() is None)
        if port is not None:
            # 以端口为准（兼容外部已启动的工具）
            return port_open(port)
        return alive

    def stop(self, slug: str) -> bool:
        proc = self._procs.pop(slug, None)
        if not proc:
            return False
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        return True


registry = ProcessRegistry()
