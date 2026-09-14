"""subtitle-viewer 纯逻辑：字幕 md 收集与 manifest 条目构建（sync / dev_server 共用）。"""
from __future__ import annotations

import re
from pathlib import Path

# `MM:SS → MM:SS` 或 `HH:MM:SS → HH:MM:SS`（反引号包裹，bilibili-subtitles 生成格式）
TS_RE = re.compile(r"`(\d{1,2}:\d{2}(?::\d{2})?)\s*→\s*(\d{1,2}:\d{2}(?::\d{2})?)`")


def parse_ts(s: str) -> int:
    """'00:00:06' / '0:06' -> 秒。"""
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 3:
        h, m, sec = parts
        return h * 3600 + m * 60 + sec
    m, sec = parts
    return m * 60 + sec


def has_timestamps(text: str) -> bool:
    return TS_RE.search(text) is not None


def _natural_key(s: str) -> list[tuple[int, object]]:
    """自然序键：数字段按数值比较，其余按原文（'Unit 2' < 'Unit 10'，'Part 1' < 'Part 2'）。"""
    return [(int(p), "") if p.isdigit() else (0, p) for p in re.split(r"(\d+)", s)]


def collect_docs(root: Path) -> list[dict]:
    """递归收集含时间戳的 .md（跳过 _ 开头的目录/文件），按标题自然序（Unit 升序）返回 manifest 条目。"""
    root = Path(root)
    docs: list[dict] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part.startswith("_") for part in rel.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        stamps = TS_RE.findall(text)
        if not stamps:
            continue
        docs.append({
            "path": rel.as_posix(),
            "title": p.stem,
            "count": len(stamps),
            "duration": max(parse_ts(end) for _, end in stamps),
        })
    docs.sort(key=lambda d: _natural_key(d["title"]))
    return docs
