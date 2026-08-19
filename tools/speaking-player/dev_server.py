"""本地开发服务器：托管静态文件；/tracks/ 返回与 nginx autoindex json 相同格式的列表。

用法：python dev_server.py [port]   # 默认 8400
"""
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE = Path(__file__).resolve().parent
TRACKS_DIR = BASE / "fixtures" / "tracks"


def _entry(name, full):
    return {
        "name": name,
        "type": "directory" if os.path.isdir(full) else "file",
        "mtime": datetime.fromtimestamp(os.path.getmtime(full), tz=timezone.utc)
        .strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }


def build_autoindex(dirpath):
    """nginx autoindex_format json 同构列表。纯函数，可单测。"""
    return [_entry(n, os.path.join(dirpath, n)) for n in sorted(os.listdir(dirpath))]


def to_disk(url_path):
    """URL -> 磁盘路径：/tracks/** 映射 fixtures/tracks/**。纯函数，可单测。"""
    rel = unquote(url_path).lstrip("/")
    if rel == "tracks" or rel.startswith("tracks/"):
        sub = rel[len("tracks/"):] if rel.startswith("tracks/") else ""
        return TRACKS_DIR / sub
    p = BASE / rel
    return p if p.suffix else BASE / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        disk = to_disk(path)
        if path.rstrip("/") == "/tracks" or path.startswith("/tracks/"):
            if disk.is_dir():
                self._send_json(build_autoindex(disk))
                return
            if disk.is_file():
                self._send_file(disk)
                return
            self.send_error(404, "Not Found")
            return
        if path == "/":
            disk = BASE / "index.html"
        if disk.is_file():
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

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(port=8400):
    print(f"dev server on http://127.0.0.1:{port}/   (tracks -> {TRACKS_DIR})")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8400)
