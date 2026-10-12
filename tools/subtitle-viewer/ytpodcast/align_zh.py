"""欧路整段中文 → 英文句块对齐(无头 claude),产物 翻译/EPxx-align.txt。

提示词规则沿用 bilibili-subtitles/alignment_agent.py;runner 自带文件重定向版——
capture_output 管道在 Windows 上超时杀进程时会悬挂(子进程握管道不松手),改为
cmd 重定向到临时文件,超时也能拿到已产出内容。中文来源:翻译/EPxx-中文.txt,
首行是欧路连标题一起翻的产物,跳过;余下行无缝拼接(接缝修复交给排版提示词)。

用法(在 tools/subtitle-viewer 下):
  python -m ytpodcast.align_zh [--only EP01] [--force]
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR.parent.parent / "bilibili-subtitles"))
sys.path.insert(0, str(TOOL_DIR.parent))

from ytpodcast.build import episodes, merge_cues, parse_vtt, split_align_blocks  # noqa: E402

ALIGN_TIMEOUT_SECONDS = 1800

PROMPT_TEMPLATE = """你是双语字幕排版器。任务:把整段中文译文按英文字幕块的断句点切分对齐。

规则:
1. 共 {count} 个英文字幕块,输出必须正好 {count} 段中文,按顺序一一对应。
2. 每段中文单独成块,块与块之间空一行;不要序号、不要解释、不要 markdown 代码块。
3. 句中被切断的块,中文跟着同一语义点切断,跨块连读仍是完整通顺的一句。
4. 译文以给定中文为准,只修明显硬伤(错字、换行接缝断裂、拼音转写错误),不要改写风格。
5. 任何一段都不能为空;某块英文对应的中文极短时给几个字即可。
6. 中文译文的覆盖范围之外(译文被截断)的英文块,该段只写一个 · 占位符。

英文字幕块:
{blocks}

整段中文译文:
{chinese}
"""


def run_claude_to_file(prompt: str, out_path: Path,
                       timeout: int = ALIGN_TIMEOUT_SECONDS) -> str:
    """无头 claude:stdin 进,stdout/stderr 直写文件句柄(不经内存管道,超时杀进程无悬挂)。"""
    executable = shutil.which("claude")
    if not executable:
        raise RuntimeError("未找到 claude 命令——排版需要本机已安装 Claude Code 并在 PATH 中")
    command: list[str] = [executable, "-p", "--output-format", "text"]
    if executable.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", *command]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    err_path = Path(str(out_path) + ".err")
    try:
        with open(out_path, "w", encoding="utf-8") as fo, \
                open(err_path, "w", encoding="utf-8") as fe:
            try:
                subprocess.run(command, input=prompt, stdout=fo, stderr=fe,
                               text=True, encoding="utf-8", timeout=timeout)
            except subprocess.TimeoutExpired:
                pass                                     # 文件里可能已有内容,继续校验
    finally:
        err_path.unlink(missing_ok=True)
    content = out_path.read_text(encoding="utf-8", errors="replace").strip() \
        if out_path.exists() else ""
    out_path.unlink(missing_ok=True)
    if not content:
        raise RuntimeError("claude 无输出(超时或启动失败)")
    return content


def load_chinese(zh_path: Path) -> str:
    """读欧路译文:跳过首行标题,余下无缝拼接(中文不吃空格)。"""
    lines = zh_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "".join(lines[1:]).strip()


def find_zh_file(zh_dir: Path, ep_id: str) -> Path | None:
    for cand in zh_dir.glob(f"{ep_id}-中文.*"):
        return cand
    for cand in zh_dir.glob(f"{ep_id.lower()}-中文.*"):
        return cand
    return None


def align_episode(blocks: list[dict], chinese: str, tmp_dir: Path) -> list[str]:
    prompt = PROMPT_TEMPLATE.format(
        count=len(blocks),
        blocks="\n".join(f"[{i + 1:03d}] {b['text']}" for i, b in enumerate(blocks)),
        chinese=chinese,
    )
    out = run_claude_to_file(prompt, tmp_dir / "_align_out.tmp")
    zh = split_align_blocks(out)
    if len(zh) != len(blocks):
        raise RuntimeError(f"对齐块数不符: {len(zh)}/{len(blocks)}")
    return zh


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="欧路中文 → EPxx-align.txt")
    ap.add_argument("--only", default=None, help="只处理指定集,如 EP01")
    ap.add_argument("--force", action="store_true", help="align 已存在也重跑")
    args = ap.parse_args(argv)

    import json as _json
    config = _json.loads((TOOL_DIR.parent / "config.json").read_text(encoding="utf-8"))
    src = Path(config["src_root"]) / "youtube-podcast"
    zh_dir = src / "翻译"

    done = fail = skip = 0
    for stem, vtt in episodes(src):
        ep_id = stem[:4]
        if args.only and ep_id != args.only:
            continue
        zh_file = find_zh_file(zh_dir, ep_id)
        if not zh_file:
            print(f"{ep_id}: 无中文文件,跳过")
            skip += 1
            continue
        out_file = zh_dir / f"{ep_id}-align.txt"
        if out_file.is_file() and not args.force:
            print(f"{ep_id}: align 已存在,跳过(--force 重跑)")
            skip += 1
            continue
        blocks = merge_cues(parse_vtt(vtt.read_text(encoding="utf-8", errors="replace")))
        chinese = load_chinese(zh_file)
        try:
            zh = align_episode(blocks, chinese, zh_dir)
        except Exception as exc:
            print(f"{ep_id}: ✗ {exc}")
            fail += 1
            continue
        out_file.write_text("\n\n".join(zh) + "\n", encoding="utf-8")
        covered = sum(1 for z in zh if z.strip() != "·")
        if covered < len(zh):                                  # 截断:生成剩余英文供二次欧路
            cut = max(i for i, z in enumerate(zh) if z.strip() != "·") + 1
            remain = " ".join(b["text"] for b in blocks[cut:])
            (zh_dir / f"{ep_id}-英文2.txt").write_text(
                f"# {ep_id} 剩余英文({len(blocks) - cut} 块,接上一段译文末尾)\n\n{remain}",
                encoding="utf-8")
            print(f"{ep_id}: ✓ {covered}/{len(zh)} 段对齐(截断于第 {cut} 块)→ 已生成 {ep_id}-英文2.txt")
        else:
            print(f"{ep_id}: ✓ {len(zh)} 段对齐(全覆盖)")
        done += 1
    print(f"完成 {done},失败 {fail},跳过 {skip}")


if __name__ == "__main__":
    main()
