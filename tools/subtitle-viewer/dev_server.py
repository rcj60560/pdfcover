"""本地开发服务器：托管前端静态文件；/docs/** 映射本地字幕目录；/manifest.json 动态生成。

用法：python dev_server.py [port] [--lan]   # 默认 8800
"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from subtitle_lib import collect_docs

BASE = Path(__file__).resolve().parent


def resolve_docs_dir(cfg: Path = BASE / "config.json",
                     fallback: Path = BASE / "fixtures" / "docs") -> Path:
    """config.json 的 src_root 存在则用之，否则 fixtures。纯函数，可单测。"""
    if cfg.is_file():
        try:
            root = json.loads(cfg.read_text(encoding="utf-8")).get("src_root", "")
            if root and Path(root).is_dir():
                return Path(root)
        except (OSError, ValueError):
            pass
    return fallback


DOCS_DIR = resolve_docs_dir()


def to_disk(url_path: str, docs_dir: Path | None = None) -> Path:
    """URL -> 磁盘路径：/docs/** 映射字幕目录。纯函数，可单测。"""
    docs_dir = docs_dir if docs_dir is not None else DOCS_DIR
    rel = unquote(url_path).lstrip("/")
    if ".." in rel.replace("\\", "/").split("/"):
        raise ValueError("路径不允许包含 ..")
    if rel == "docs" or rel.startswith("docs/"):
        sub = rel[len("docs/"):] if rel.startswith("docs/") else ""
        return docs_dir / sub
    p = BASE / rel
    return p if p.suffix else BASE / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/manifest.json":
            self._send_json({"docs": collect_docs(DOCS_DIR)})
            return
        try:
            disk = to_disk(path)
        except ValueError:
            self.send_error(404, "Not Found")
            return
        if path.rstrip("/") == "/docs" or path.startswith("/docs/"):
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
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
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
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def lan_ip() -> str:
    """取本机局域网 IP（连不上外网时退化为主机名解析）。"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def main(port=8800, lan=False):
    host = "0.0.0.0" if lan else "127.0.0.1"
    if lan:
        print(f"dev server on http://127.0.0.1:{port}/  and  http://{lan_ip()}:{port}/   (LAN，手机同一 Wi-Fi 可访问)")
    else:
        print(f"dev server on http://127.0.0.1:{port}/   (docs -> {DOCS_DIR})")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    argv = sys.argv[1:]
    lan = "--lan" in argv
    args = [a for a in argv if a != "--lan"]
    main(int(args[0]) if args else 8800, lan=lan)
