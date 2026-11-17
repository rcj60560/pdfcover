"""批量模式纯逻辑:数据结构、范围解析、退避、枚举解析、落盘、队列状态机。

无 Flask / 无网络 / 无线程:可注入依赖,离线可测。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_INTERVAL_SEC = 60
_BACKOFF_LADDER = (60, 300, 900)  # 1→5→15 分钟,封顶 900


@dataclass
class BatchItem:
    p: int
    title: str
    duration: int
    status: str = "queued"  # queued | running | done | failed
    job_id: str | None = None
    error: str = ""
    attempts: int = 0


@dataclass
class Batch:
    batch_id: str
    source_url: str
    title: str
    items: list[BatchItem] = field(default_factory=list)
    interval_sec: int = DEFAULT_INTERVAL_SEC
    state: str = "running"  # running | finished
    created_at: str = ""


def parse_ps(text: str, available: int) -> list[int]:
    """'1-10,15' → 升序去重的 p 号列表(1 起,越界截断);非法片段抛 ValueError。"""
    result: set[int] = set()
    for raw in (text or "").split(","):
        token = raw.strip()
        if not token:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)|(\d+)", token)
        if not m:
            raise ValueError(f"无法理解的集数范围片段:{token!r}(示例:1-10,15)")
        if m.group(3):
            result.add(int(m.group(3)))
        else:
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            result.update(range(lo, hi + 1))
    return sorted(p for p in result if 1 <= p <= available)


def backoff_seconds(attempts: int) -> int:
    """第 attempts 次(1 起)失败后的退避秒数:60→300→900,封顶 900。"""
    if attempts <= 0:
        return 0
    return _BACKOFF_LADDER[min(attempts, len(_BACKOFF_LADDER)) - 1]
