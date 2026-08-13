"""本地学习站点：托管本目录静态文件，根路径返回 index.html（学习路线主页）。

用法：
    python dev_server.py [port]      # 默认 7000

设计同 audio-player/dev_server.py：纯标准库，无第三方依赖。
页面（index.html）、notes/、code/、cheatsheet/ 均从脚本所在目录提供。
"""

import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))


def to_disk(url_path: str) -> str:
    """URL 路径 -> 磁盘路径。根或目录请求 -> index.html。"""
    rel = unquote(url_path).lstrip("/")
    if rel == "":
        return os.path.join(BASE, "index.html")
    return os.path.join(BASE, rel)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        disk = to_disk(path)

        # 目录请求（如 /notes/）-> 自动找该目录下的 index.html 或 README.md
        if disk != os.path.join(BASE, "index.html") and os.path.isdir(disk):
            for idx in ("index.html", "README.md"):
                candidate = os.path.join(disk, idx)
                if os.path.isfile(candidate):
                    disk = candidate
                    break

        if os.path.isfile(disk):
            self._send_file(disk)
            return
        self.send_error(404, "Not Found")

    def _send_file(self, disk: str):
        with open(disk, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(disk)[0]
        # .md 文件让浏览器直接显示文本，而不是下载
        if disk.endswith(".md"):
            ctype = "text/plain; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # 静音默认日志
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(port: int = 7000):
    print(f"agent-learning on http://127.0.0.1:{port}/   (root={BASE})")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7000)
