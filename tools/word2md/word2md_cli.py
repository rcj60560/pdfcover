"""命令行版：Word(.docx) → Markdown（pandoc）。

用法（任意目录）：
    python word2md_cli.py 需求说明书.docx                 # → 同目录 需求说明书.md + 图片和附件/
    python word2md_cli.py 图片和附件/说明书.docx           # → 上一级 说明书.md，图片并入 图片和附件/
    python word2md_cli.py 说明书.docx -o out/说明书.md --media-dir assets

不带参数运行则提示输入路径（面板启动/双击也能用，可直接把文件拖进窗口）。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import word2md_core as core


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Word(.docx) → Markdown（pandoc）")
    ap.add_argument("file", nargs="?", help="Word(.docx) 文件路径")
    ap.add_argument("-o", "--output", default=None, help="输出 .md 路径（默认同目录同名）")
    ap.add_argument("--media-dir", default=None,
                    help=f"图片抽取目录（默认输出目录下的 {core.DEFAULT_MEDIA_DIR}/）")
    args = ap.parse_args(argv)

    if not args.file:
        args.file = input("拖入或粘贴 Word(.docx) 文件路径: ").strip().strip('"').strip("'")
    if not args.file:
        ap.error("必须提供 .docx 文件路径")

    result = core.convert(args.file, output_md=args.output, media_dir=args.media_dir)
    print(result.md)
    print(f"图片 {result.images} 张 → {result.media}" if result.media else "文档无图片")


if __name__ == "__main__":
    main()
