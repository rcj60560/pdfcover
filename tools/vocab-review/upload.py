"""一键部署：web/ 前端五件套 → 服务器 vocab 站点。

用法：python upload.py [--build] [--dir NAME] [--vocab FILE]
--build 先用同一解释器重跑 build.py 生成 vocab.json 再上传。
--dir  远程子目录名（script/ 之下），默认 vocab；如 vocab-beta 走 beta 站点。
--vocab 指定本地词库文件推为远程 vocab.json（默认 web/vocab.json；beta 用 web/vocab-beta.json）。
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_ROOT = "/www/wwwroot/47.108.230.162/script"
WEB_NAMES = ("index.html", "app.js", "core.js", "style.css")  # vocab.json 单独推（可指定来源文件）


def run(cmd: list[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="上传 web/ 五件套到服务器 vocab 目录")
    ap.add_argument("--build", action="store_true", help="先跑 build.py 重新生成 vocab.json")
    ap.add_argument("--dir", default="vocab", help="远程子目录名（script/ 之下），默认 vocab")
    ap.add_argument("--vocab", type=Path, default=None,
                    help="本地词库文件，推为远程 vocab.json（默认 web/vocab.json）")
    args = ap.parse_args(argv)

    if args.build:
        print("$", sys.executable, "build.py")
        subprocess.run([sys.executable, "build.py"], check=True, cwd=TOOL_DIR)

    remote_base = f"{REMOTE_ROOT}/{args.dir}"
    vocab_file = TOOL_DIR / "web" / "vocab.json" if args.vocab is None else args.vocab
    files = [TOOL_DIR / "web" / n for n in WEB_NAMES] + [vocab_file]
    missing = [f.name for f in files if not f.is_file()]
    if missing:
        sys.exit(f"缺文件（先跑 build.py?）：{'、'.join(missing)}")

    run(["ssh", REMOTE_HOST, f"mkdir -p {shlex.quote(remote_base)}"])
    for f in files:
        # vocab 来源文件名可能不同（如 vocab-beta.json），远程一律落名 vocab.json
        dest = f"{remote_base}/vocab.json" if f == vocab_file else f"{remote_base}/"
        run(["scp", str(f), f"{REMOTE_HOST}:{dest}"])
    run(["ssh", REMOTE_HOST, f"chown -R www:www {shlex.quote(remote_base)}"])
    print(f"完成：{len(files)} 个文件 → {remote_base}（vocab.json ← {vocab_file.name}）")


if __name__ == "__main__":
    main()
