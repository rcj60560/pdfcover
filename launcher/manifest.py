"""解析 tools/*/tool.toml → Tool 列表（纯逻辑，可单测）。"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib  # type: ignore


@dataclass
class Tool:
    slug: str
    name: str
    desc: str
    category: str
    status: str          # "ready" | "planned"
    cmd: list[str]
    port: int | None
    url: str
    live: str
    dir: Path


def load_tools(tools_dir: Path) -> list[Tool]:
    """扫描 tools_dir 下每个含 tool.toml 的子目录（跳过 _ 开头），按 slug 排序返回。"""
    tools: list[Tool] = []
    if not tools_dir.is_dir():
        return tools
    for child in sorted(tools_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        toml = child / "tool.toml"
        if not toml.is_file():
            continue
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
        run = data.get("run", {})
        links = data.get("links", {})
        tools.append(
            Tool(
                slug=child.name,
                name=data.get("name", child.name),
                desc=data.get("desc", ""),
                category=data.get("category", ""),
                status=data.get("status", "ready"),
                cmd=list(run.get("cmd", [])),
                port=run.get("port"),
                url=run.get("url", ""),
                live=links.get("live", ""),
                dir=child,
            )
        )
    return tools
