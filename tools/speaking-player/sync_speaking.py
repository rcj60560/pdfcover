"""一键同步：本地口语音频目录 → 服务器 speaking 站点。

用法：
    python sync_speaking.py [--src 目录] [--dry-run]

默认源目录读 ../text2mp3/config.json 的 out_dir；
目标 root@47.108.230.162:/www/wwwroot/47.108.230.162/script/speaking/（tracks/ + 前端4文件）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_BASE = "/www/wwwroot/47.108.230.162/script/speaking"


def collect_media(src: Path) -> list[Path]:
    """src 下的 .mp3 与 .json（按文件名排序）。"""
    return sorted(p for p in src.iterdir()
                  if p.is_file() and p.suffix.lower() in (".mp3", ".json"))


def front_files(tool_dir: Path) -> list[Path]:
    """要上传的前端静态文件（存在的才算）。"""
    names = ("index.html", "app.js", "core.js", "style.css")
    return [tool_dir / n for n in names if (tool_dir / n).is_file()]


def default_src() -> Path:
    cfg = TOOL_DIR.parent / "text2mp3" / "config.json"
    out = json.loads(cfg.read_text(encoding="utf-8"))["out_dir"] if cfg.is_file() else ""
    return Path(out) if out else Path(r"D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频")


def run(cmd: list[str], dry: bool) -> None:
    printable = " ".join(str(c) for c in cmd)
    print("$", printable)
    if not dry:
        subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="同步口语音频与前端到服务器")
    ap.add_argument("--src", type=Path, default=default_src(), help="本地音频目录")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    args = ap.parse_args(argv)

    media = collect_media(args.src)
    fronts = front_files(TOOL_DIR)
    if not media:
        sys.exit(f"源目录没有 mp3/json：{args.src}")

    run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/tracks"], args.dry_run)
    for f in fronts:
        run(["scp", str(f), f"{REMOTE_HOST}:{REMOTE_BASE}/"], args.dry_run)
    if media:
        run(["scp", *[str(p) for p in media], f"{REMOTE_HOST}:{REMOTE_BASE}/tracks/"], args.dry_run)
    run(["ssh", REMOTE_HOST, f"chown -R www:www {REMOTE_BASE}"], args.dry_run)
    print(f"完成：{len(fronts)} 个前端文件 + {len(media)} 个媒体文件")


if __name__ == "__main__":
    main()
