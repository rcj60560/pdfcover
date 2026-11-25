"""PDF → 干净 TXT(给 Language Reactor 等阅读器导入用)。

用法: python pdf2txt.py <输入.pdf> [-o 输出.txt]
- 文字版 PDF: pypdf 直接抽文本(秒出)
- 扫描版 PDF(抽不出字): 自动走 ocrmypdf OCR 后再抽(需 Tesseract,见 install_tesseract.bat)
- 清理: 去页眉页脚式断行、合并被硬换行拆开的句子、去多余空行
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader

MIN_CHARS_PER_PAGE = 50  # 低于此视为扫描版(没文字层)


def extract(pdf: Path) -> tuple[str, bool]:
    """返回 (文本, 是否有文字层)。"""
    reader = PdfReader(str(pdf))
    pages = [(p.extract_text() or "") for p in reader.pages]
    has_text = sum(len(t.strip()) for t in pages) / max(1, len(pages)) >= MIN_CHARS_PER_PAGE
    return "\n\n".join(pages), has_text


def ocr(pdf: Path) -> str:
    """扫描版: ocrmypdf 加文字层后再抽。失败给可操作提示。"""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ocr.pdf"
        try:
            subprocess.run(
                ["python", "-m", "ocrmypdf", "--force-ocr", "-l", "eng", str(pdf), str(out)],
                check=True, capture_output=True, text=True, timeout=1800,
            )
        except FileNotFoundError:
            sys.exit("缺 ocrmypdf: pip install ocrmypdf")
        except subprocess.CalledProcessError as exc:
            hint = (exc.stderr or "").strip().splitlines()
            sys.exit(f"OCR 失败(多半是没装 Tesseract,见 install_tesseract.bat):\n  " +
                     "\n  ".join(hint[-3:] if hint else str(exc)))
        text, _ = extract(out)
        return text


def clean(text: str) -> str:
    """合并硬换行、去页眉页脚残留、压空行。"""
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if re.fullmatch(r"(Page\s*)?\d{1,4}(\s*of\s*\d{1,4})?", line, re.I):
            continue  # 纯页码
        if out and out[-1] and not re.search(r"[.!?。！？:：;；]$", out[-1]) and not out[-1].endswith("—"):
            out[-1] = out[-1] + " " + line  # 上一行没结句 → 合并(英文硬换行)
        else:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="PDF → 干净 TXT")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="默认: 同目录同名 .txt")
    args = ap.parse_args()
    pdf: Path = args.pdf
    if not pdf.is_file():
        sys.exit(f"文件不存在: {pdf}")
    text, has_text = extract(pdf)
    if not has_text:
        print("扫描版 PDF(无文字层),走 OCR…", file=sys.stderr)
        text = ocr(pdf)
    out: Path = args.output or pdf.with_suffix(".txt")
    out.write_text(clean(text), encoding="utf-8")
    print(f"完成: {out}  ({len(text)} 字符, {'文字版直抽' if has_text else 'OCR'})")


if __name__ == "__main__":
    main()
