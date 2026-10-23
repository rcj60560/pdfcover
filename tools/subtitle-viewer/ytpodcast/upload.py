"""youtube-podcast 定点上集:新集 md+mp3 直传 47 站,manifest 本地重建单传。

sync_subtitles.py 全量 = 每文件一连接,连跑触发 47 服务器 SSH 连接限流;
本工具只传指定集(一集 md/mp3 各一连接)+ manifest 一传 + chown 一连。

用法(在 tools/subtitle-viewer 下):
  python -m ytpodcast.upload EP11 EP12      # 上指定集
  python -m ytpodcast.upload --all-new      # 上远端还没有 md 的所有集
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

from subtitle_lib import collect_docs

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
SUB_BASE = "/www/wwwroot/47.108.230.162/script/subtitles"
DOC_DIR = f"{SUB_BASE}/docs/youtube-podcast"
AUDIO_DIR = "/www/wwwroot/47.108.230.162/script/books/youtube-podcast"


def run(cmd: list[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def upload(remote: str, local: Path) -> None:
    run(["scp", str(local), f"{REMOTE_HOST}:{remote}"])


def push_manifest(src_root: Path) -> None:
    """本地全量重建 manifest(与 sync_subtitles.py 同构),单连接上传。"""
    docs = collect_docs(src_root)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump({"docs": docs}, f, ensure_ascii=False, indent=2)
        tmp = f.name
    try:
        upload(f"{SUB_BASE}/manifest.json", Path(tmp))
    finally:
        Path(tmp).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="youtube-podcast 定点上集(md+mp3+manifest)")
    ap.add_argument("eps", nargs="*", help="集号,如 EP11")
    ap.add_argument("--all-new", action="store_true", help="上远端还没有 md 的所有集")
    args = ap.parse_args(argv)
    if not args.eps and not args.all_new:
        ap.error("给集号(EP11 EP12…)或 --all-new")

    config = json.loads((TOOL_DIR.parent / "config.json").read_text(encoding="utf-8"))
    src_root = Path(config["src_root"])
    src = src_root / "youtube-podcast"

    eps = [e.upper() for e in args.eps]
    if args.all_new:
        remote = subprocess.run(
            ["ssh", REMOTE_HOST, f"ls {shlex.quote(DOC_DIR)}"],
            capture_output=True, text=True, check=True).stdout
        have = {n[:4] for n in remote.splitlines() if n.strip()}
        eps = sorted({p.name[:4] for p in src.glob("EP*.md")} - have)
        if not eps:
            print("远端已是最新,没有新集")
            return

    run(["ssh", REMOTE_HOST, f"mkdir -p {shlex.quote(DOC_DIR)} {shlex.quote(AUDIO_DIR)}"])
    done = fail = 0
    for ep in eps:
        md = next(iter(src.glob(f"{ep}*.md")), None)
        mp3 = next(iter(src.glob(f"{ep}*.mp3")), None)
        if not md or not mp3:
            miss = "md" if not md and not mp3 else ("md" if not md else "mp3")
            print(f"{ep}: ✗ 缺{miss},先跑 build")
            fail += 1
            continue
        upload(f"{DOC_DIR}/{md.name}", md)
        upload(f"{AUDIO_DIR}/{mp3.name}", mp3)
        print(f"{ep}: ✓ md({md.stat().st_size // 1024}KB) + mp3({mp3.stat().st_size // 2**20}MB)")
        done += 1
    push_manifest(src_root)
    run(["ssh", REMOTE_HOST,
         f"chown -R www:www {shlex.quote(DOC_DIR)} {shlex.quote(AUDIO_DIR)}"
         f" {shlex.quote(SUB_BASE + '/manifest.json')}"])
    print(f"上传 {done} 集,失败 {fail}")


if __name__ == "__main__":
    main()
