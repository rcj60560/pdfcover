"""word2md 核心逻辑：subprocess 调 pandoc 把 .docx 转成 GitHub 风格 Markdown。

纯逻辑无 CLI，方便单测。关键约定：
- pandoc 以输出 md 所在目录为 cwd、-o/--extract-media 均传相对名，保证 md 里图片引用相对路径正确；
- pandoc 会把图片塞进 <目录>/media/ 子层并输出 <img> 标签，转换后统一拍平、改写成 ![]()；
- 输出默认遵循 devdocs 归档习惯：docx 在 图片和附件/ 里 → md 放到上一级并复用该目录存图。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MEDIA_DIR = "图片和附件"
# -t gfm（不关 raw_html）：复杂表格降级成 HTML 而不是丢成 [TABLE]；--wrap=none：中文不被硬换行切碎
PANDOC_ARGS = ["-f", "docx", "-t", "gfm", "--wrap=none"]
PANDOC_TIMEOUT = 300
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff",
              ".emf", ".wmf", ".svg", ".webp"}

# pandoc 输出的 <img src="..." [alt="..."] .../> → ![alt](src)
IMG_RE = re.compile(r'<img\s+src="([^"]+)"(?:\s+alt="([^"]*)")?[^>]*/?>')


class PandocNotFound(RuntimeError):
    """本机没装 pandoc。"""


class NotDocxError(ValueError):
    """输入不是 .docx（.doc 老格式 pandoc 不支持）。"""


@dataclass
class ConvertResult:
    md: Path            # 输出 md 完整路径
    media: Path | None  # 图片目录（无图时为 None）
    images: int         # 抽取出的图片张数


def find_pandoc() -> str:
    exe = shutil.which("pandoc")
    if not exe:
        raise PandocNotFound("未找到 pandoc，先安装：winget install --id JohnMacFarlane.Pandoc")
    return exe


@dataclass
class _Paths:
    src: Path   # 输入 docx（绝对路径）
    out: Path   # 输出 md（绝对路径）
    media: Path  # 图片目录（绝对路径）


def resolve_paths(input_file: str | Path, output_md: str | Path | None = None,
                  media_dir: str | Path | None = None) -> _Paths:
    """定下输出 md 与图片目录的落点。

    - output_md 未指定：docx 同目录同名 .md；若 docx 就躺在 图片和附件/ 里，
      则 md 放到上一级（归档习惯：X/图片和附件/说明书.docx → X/说明书.md）。
    - media_dir 未指定：md 所在目录下的 图片和附件/；若 docx 本就在某个
      图片和附件/ 里且输出也在上一级，则直接复用那个目录（新图并进旧图）。
    """
    src = Path(input_file)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在：{src}")
    src = src.resolve()
    if src.suffix.lower() == ".doc":
        raise NotDocxError(f"{src.name} 是老版 .doc，请先用 Word/WPS 另存为 .docx 再转")
    if src.suffix.lower() != ".docx":
        raise NotDocxError(f"只支持 .docx，收到：{src.name}")

    if output_md:
        out = Path(output_md)
        out = out if out.suffix == ".md" else out.with_suffix(".md")
    elif src.parent.name == DEFAULT_MEDIA_DIR:
        out = src.parent.parent / f"{src.stem}.md"
    else:
        out = src.with_suffix(".md")
    out = out.resolve()

    if media_dir:
        media = Path(media_dir)
        media = media if media.is_absolute() else out.parent / media
    elif output_md is None and src.parent.name == DEFAULT_MEDIA_DIR:
        media = src.parent          # 复用 docx 所在的 图片和附件/
    else:
        media = out.parent / DEFAULT_MEDIA_DIR
    return _Paths(src=src, out=out, media=media.resolve())


def build_command(pandoc: str, p: _Paths) -> list[str]:
    """pandoc 命令行：输入可绝对路径，输出/抽图传相对名（cwd=输出目录）。"""
    media_ref = media_ref_for(p)
    return [pandoc, str(p.src), *PANDOC_ARGS, "-o", p.out.name,
            "--extract-media", media_ref]


def media_ref_for(p: _Paths) -> str:
    """图片目录相对输出 md 的引用名（md 里的引用就长这样，恒为正斜杠）。"""
    try:
        return p.media.relative_to(p.out.parent).as_posix()
    except ValueError:              # 用户传了别的盘符等，退回绝对路径
        return p.media.as_posix()


def _flatten_media(media: Path) -> None:
    """把 pandoc 强加的 media/ 子层拍平（图片和附件/media/x.png → 图片和附件/x.png）。

    copy+unlink 而非 move：重转同一文档时目标图已存在，move 在 Windows 上会报错。
    """
    nested = media / "media"
    if not nested.is_dir():
        return
    for f in nested.iterdir():
        shutil.copyfile(f, media / f.name)
        f.unlink()
    nested.rmdir()


def rewrite_md(md: Path, media_ref: str) -> None:
    """md 后处理：去掉引用里多余的 media/ 层；<img> 改写成 ![]()。"""
    text = md.read_text(encoding="utf-8")
    text = text.replace(f"{media_ref}/media/", f"{media_ref}/")
    text = IMG_RE.sub(lambda m: f"![{m.group(2) or ''}]({m.group(1)})", text)
    md.write_text(text, encoding="utf-8")


def convert(input_file: str | Path, output_md: str | Path | None = None,
            media_dir: str | Path | None = None) -> ConvertResult:
    """入口：.docx → .md（+图片），返回落点信息。"""
    pandoc = find_pandoc()
    p = resolve_paths(input_file, output_md, media_dir)

    p.out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(          # cwd=输出目录，相对引用才能对齐
        build_command(pandoc, p), cwd=p.out.parent,
        capture_output=True, text=True, encoding="utf-8", timeout=PANDOC_TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pandoc 转换失败（{proc.returncode}）：{proc.stderr.strip()}")

    media_ref = media_ref_for(p)
    _flatten_media(p.media)
    rewrite_md(p.out, media_ref)

    # 按扩展名数图片：复用 图片和附件/ 时里面还有源 docx 等非图片文件，不能一并计入
    images = [f for f in p.media.iterdir()
              if f.is_file() and f.suffix.lower() in IMAGE_EXTS] if p.media.is_dir() else []
    if p.media.is_dir() and not any(p.media.iterdir()):
        p.media.rmdir()             # 无图不留空目录（非空如复用目录则不动）
    return ConvertResult(md=p.out, media=p.media if images else None, images=len(images))
