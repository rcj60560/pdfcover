"""本地开发服务器：托管 ielts-topics 静态文件。

用法：python dev_server.py [port] [--lan]   # 默认 8500
"""
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE = Path(__file__).resolve().parent


def to_disk(url_path):
    """URL -> 磁盘路径：目录穿越返回 None，无后缀回落 index.html。纯函数，可单测。"""
    rel = unquote(url_path).lstrip("/")
    if not rel:
        return BASE / "index.html"
    p = (BASE / rel).resolve()
    if not p.is_relative_to(BASE):
        return None
    return p if p.suffix else BASE / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        disk = to_disk(urlparse(self.path).path)
        if disk is None:
            self.send_error(403, "Forbidden")
            return
        if disk.is_file():
            self._send_file(disk)
            return
        self.send_error(404, "Not Found")

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
        s.connect(("8.8.8.8", 80))   # 不会真发包，只为让系统选默认路由的地址
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def main(port=8500, lan=False):
    host = "0.0.0.0" if lan else "127.0.0.1"
    if lan:
        print(f"dev server on http://127.0.0.1:{port}/  and  http://{lan_ip()}:{port}/   (LAN，手机同一 Wi-Fi 可访问)")
    else:
        print(f"dev server on http://127.0.0.1:{port}/")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--lan"]
    lan = "--lan" in sys.argv
    main(int(args[0]) if args else 8500, lan=lan)
