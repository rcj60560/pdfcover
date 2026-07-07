"""本地开发服务器：托管静态文件，并对目录请求返回与 nginx `autoindex json`
完全相同格式的 JSON，使本地验证与线上一致。

用法：
    python dev_server.py [port]      # 默认 8000

页面文件（index.html/app.js/style.css）从脚本所在目录提供；
/books/** 映射到 fixtures/books/**。
"""

import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
BOOKS_DIR = os.path.join(BASE, "fixtures", "books")


def _entry(name, full):
    typ = "directory" if os.path.isdir(full) else "file"
    mtime = datetime.fromtimestamp(os.path.getmtime(full), tz=timezone.utc)
    return {
        "name": name,
        "type": typ,
        "mtime": mtime.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }


def build_autoindex(dirpath):
    """返回与 nginx autoindex_format json 一致结构的列表。纯函数，可单测。"""
    return [
        _entry(n, os.path.join(dirpath, n))
        for n in sorted(os.listdir(dirpath))
    ]


def to_disk(url_path):
    """URL 路径 -> 磁盘路径。/books/** 映射到 fixtures/books/**。"""
    rel = unquote(url_path).lstrip("/")
    if rel == "books" or rel.startswith("books/"):
        sub = rel[len("books/"):] if rel.startswith("books/") else ""
        return os.path.join(BOOKS_DIR, sub)
    return os.path.join(BASE, rel)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        disk = to_disk(path)

        if disk.endswith(os.sep) or path.endswith("/") or os.path.isdir(disk):
            if os.path.isdir(disk):
                self._send_json(build_autoindex(disk))
                return

        if os.path.isfile(disk):
            self._send_file(disk)
            return

        self.send_error(404, "Not Found")

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, disk):
        with open(disk, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(disk)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # 静音默认日志，按需注释
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(port=8000):
    print(f"dev server on http://127.0.0.1:{port}/   (root={BASE})")
    print("books ->", BOOKS_DIR)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
