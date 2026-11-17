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


def extract_bvid(value: str) -> str:
    """从任意输入(BV号/视频页URL含?p=)提取 BV 号;没有则抛 ValueError。"""
    raw = (value or "").strip()
    m = re.search(r"(?i)(BV[0-9A-Za-z]{8,14})", raw)
    if not m:
        raise ValueError("没找到 BV 号:请贴形如 BV1gK4y1o7Ni 的合集/视频链接")
    return m.group(1)


def parse_view_api(payload: dict) -> tuple[str, list[BatchItem]]:
    """B站 view API JSON → (系列标题, 按 p 升序的 BatchItem 列表)。分P标题字段是 part。"""
    if not isinstance(payload, dict) or payload.get("code") != 0:
        message = (payload or {}).get("message") if isinstance(payload, dict) else None
        raise ValueError(f"链接无效或权限不足:B站返回 {message or payload!r:.80}")
    data = payload.get("data") or {}
    pages = data.get("pages") or []
    if not pages:
        raise ValueError("B站返回异常数据:没有分P列表")
    items = [
        BatchItem(p=int(page.get("page") or 0), title=str(page.get("part") or f"p{page.get('page')}"),
                  duration=int(page.get("duration") or 0))
        for page in pages if page.get("page")
    ]
    items.sort(key=lambda i: i.p)
    return str(data.get("title") or ""), items


def batch_to_json(batch: Batch) -> dict:
    d = asdict(batch)
    return d


def batch_from_json(d: dict) -> Batch:
    items = [BatchItem(**item) for item in d.get("items", [])]
    # 恢复语义:上次中断时 running 的集子回到排队;done/failed 原样保留
    for item in items:
        if item.status == "running":
            item.status = "queued"
    return Batch(
        batch_id=str(d.get("batch_id") or ""), source_url=str(d.get("source_url") or ""),
        title=str(d.get("title") or ""), items=items,
        interval_sec=int(d.get("interval_sec") or DEFAULT_INTERVAL_SEC),
        state=str(d.get("state") or "finished"), created_at=str(d.get("created_at") or ""),
    )


def save_batch(batch: Batch, directory: Path) -> Path:
    """原子写:先 tmp 后 os.replace,断电不留半个文件。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{batch.batch_id}.json"
    tmp = directory / f"{batch.batch_id}.json.tmp"
    tmp.write_text(json.dumps(batch_to_json(batch), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def load_batches(directory: Path) -> list[Batch]:
    out: list[Batch] = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            out.append(batch_from_json(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError, KeyError):
            continue  # 坏文件跳过,不拖垮整个启动加载
    return out
