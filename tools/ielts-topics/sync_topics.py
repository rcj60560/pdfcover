"""一键同步：ielts-topics 前端 + 话题数据 → 服务器 topics 站点。

用法：
    python sync_topics.py [--dry-run]

目标 root@47.108.230.162:/www/wwwroot/47.108.230.162/script/topics/
（index.html/app.js/core.js/style.css + data/topics.json）。
线上地址：http://47.108.230.162/script/topics/
nginx location 见 nginx.conf.example（一次性配置）。
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_BASE = "/www/wwwroot/47.108.230.162/script/topics"


def collect_files(tool_dir: Path) -> list[Path]:
    """前端 4 文件 + data/topics.json（存在的才算）。"""
    names = ("index.html", "app.js", "core.js", "style.css")
    files = [tool_dir / n for n in names if (tool_dir / n).is_file()]
    data = tool_dir / "data" / "topics.json"
    if data.is_file():
        files.append(data)
    return files


def rel_remote(f: Path) -> str:
    """本地相对工具目录的路径 → 服务器相对 REMOTE_BASE 的路径（保持 data/ 层级）。"""
    return f.relative_to(TOOL_DIR).as_posix()


def run(cmd: list[str], dry: bool) -> None:
    print("$", " ".join(str(c) for c in cmd))
    if not dry:
        subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="同步话题工具前端与数据到服务器")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    args = ap.parse_args(argv)

    files = collect_files(TOOL_DIR)
    if not files:
        raise SystemExit("没有可上传的文件")

    run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/data"], args.dry_run)
    for f in files:
        run(["scp", str(f), f"{REMOTE_HOST}:{REMOTE_BASE}/{rel_remote(f)}"], args.dry_run)
    run(["ssh", REMOTE_HOST, f"chown -R www:www {REMOTE_BASE}"], args.dry_run)
    print(f"完成：{len(files)} 个文件")


if __name__ == "__main__":
    main()
