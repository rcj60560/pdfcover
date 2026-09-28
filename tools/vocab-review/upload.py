"""一键部署：web/ 前端五件套 → 服务器 vocab 站点。

用法：python upload.py [--build]
--build 先用同一解释器重跑 build.py 生成 vocab.json 再上传。
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_BASE = "/www/wwwroot/47.108.230.162/script/vocab"
WEB_NAMES = ("index.html", "app.js", "core.js", "style.css", "vocab.json")


def run(cmd: list[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="上传 web/ 五件套到服务器 vocab 目录")
    ap.add_argument("--build", action="store_true", help="先跑 build.py 重新生成 vocab.json")
    args = ap.parse_args(argv)

    if args.build:
        print("$", sys.executable, "build.py")
        subprocess.run([sys.executable, "build.py"], check=True, cwd=TOOL_DIR)

    files = [TOOL_DIR / "web" / n for n in WEB_NAMES]
    missing = [f.name for f in files if not f.is_file()]
    if missing:
        sys.exit(f"缺文件（先跑 build.py?）：{'、'.join(missing)}")

    run(["ssh", REMOTE_HOST, f"mkdir -p {shlex.quote(REMOTE_BASE)}"])
    for f in files:
        run(["scp", str(f), f"{REMOTE_HOST}:{REMOTE_BASE}/"])
    run(["ssh", REMOTE_HOST, f"chown -R www:www {shlex.quote(REMOTE_BASE)}"])
    print(f"完成：{len(files)} 个文件 → {REMOTE_BASE}")


if __name__ == "__main__":
    main()
