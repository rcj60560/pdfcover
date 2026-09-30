"""一键部署:门户页 → 服务器站点根。

用法:python upload.py
把本目录 index.html 推为 /www/wwwroot/47.108.230.162/index.html,
即 http://47.108.230.162/ 的统一入口卡片页。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_FILE = "/www/wwwroot/47.108.230.162/index.html"


def main() -> None:
    src = TOOL_DIR / "index.html"
    if not src.is_file():
        raise SystemExit("缺 index.html")
    for cmd in (
        ["scp", str(src), f"{REMOTE_HOST}:{REMOTE_FILE}"],
        ["ssh", REMOTE_HOST, f"chown www:www {REMOTE_FILE}"],
    ):
        print("$", *cmd)
        subprocess.run(cmd, check=True)
    print(f"完成 → http://47.108.230.162/ ({REMOTE_FILE})")


if __name__ == "__main__":
    main()
