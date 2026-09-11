"""一键同步：本地字幕 md 目录 → 服务器 subtitles 站点。

用法：python sync_subtitles.py [--src 目录] [--dry-run]
默认源目录读 config.json 的 src_root。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from subtitle_lib import collect_docs

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_BASE = "/www/wwwroot/47.108.230.162/script/subtitles"
FRONT_NAMES = ("index.html", "app.js", "core.js", "style.css")


def front_files(tool_dir: Path) -> list[Path]:
    """要上传的前端静态文件（存在的才算）。"""
    return [tool_dir / n for n in FRONT_NAMES if (tool_dir / n).is_file()]


def read_src(cfg: Path = TOOL_DIR / "config.json") -> Path:
    """config.json 的 src_root；缺失/无效则回退 fixtures/docs。纯函数，可单测。"""
    if cfg.is_file():
        try:
            root = json.loads(cfg.read_text(encoding="utf-8")).get("src_root", "")
            if root:
                return Path(root)
        except (OSError, ValueError):
            pass
    return TOOL_DIR / "fixtures" / "docs"


def run(cmd: list[str], dry: bool) -> None:
    printable = " ".join(str(c) for c in cmd)
    print("$", printable)
    if not dry:
        subprocess.run(cmd, check=True)


def upload(remote: str, local: Path, dry: bool) -> None:
    run(["scp", str(local), f"{REMOTE_HOST}:{remote}"], dry)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="同步字幕与前端到服务器")
    ap.add_argument("--src", type=Path, default=None, help="本地字幕目录（默认读 config.json）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    args = ap.parse_args(argv)
    src = args.src or read_src()

    docs = collect_docs(src)
    if not docs:
        sys.exit(f"源目录没有含时间戳的 md：{src}")

    fronts = front_files(TOOL_DIR)
    run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/docs"], args.dry_run)
    for f in fronts:
        upload(f"{REMOTE_BASE}/", f, args.dry_run)
    for d in docs:
        rel = Path(d["path"])
        if str(rel.parent) != ".":
            run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/docs/{rel.parent.as_posix()}"], args.dry_run)
        upload(f"{REMOTE_BASE}/docs/{rel.as_posix()}", src / rel, args.dry_run)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"docs": docs}, f, ensure_ascii=False, indent=2)
        manifest_tmp = f.name
    upload(f"{REMOTE_BASE}/manifest.json", Path(manifest_tmp), args.dry_run)
    run(["ssh", REMOTE_HOST, f"chown -R www:www {REMOTE_BASE}"], args.dry_run)
    print(f"完成：{len(fronts)} 个前端文件 + {len(docs)} 篇字幕")


if __name__ == "__main__":
    main()
