"""词典精翻的一键排版：无头调用本机 claude，把整段中文对齐到英文字幕块。

流程外置于 app.py 之外，方便单测提示词构造与错误提示。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Sequence

import subtitle_core as core

ALIGN_TIMEOUT_SECONDS = 600

_PROMPT_TEMPLATE = """你是双语字幕排版器。任务：把整段中文译文按英文字幕块的断句点切分对齐。

规则：
1. 共 {count} 个英文字幕块，输出必须正好 {count} 段中文，按顺序一一对应。
2. 每段中文单独成块，块与块之间空一行；不要序号、不要解释、不要 markdown 代码块。
3. 句中被切断的块，中文跟着同一语义点切断，跨块连读仍是完整通顺的一句。
4. 译文以给定中文为准，只修明显硬伤（错字、换行接缝断裂、拼音转写错误），不要改写风格。
5. 任何一段都不能为空；某块英文对应的中文极短时给几个字即可。

英文字幕块：
{blocks}

整段中文译文：
{chinese}
"""


def build_align_prompt(rows: Sequence[core.BilingualRow], chinese: str) -> str:
    blocks = "\n".join(f"[{index + 1:03d}] {row.english}" for index, row in enumerate(rows))
    return _PROMPT_TEMPLATE.format(count=len(rows), blocks=blocks, chinese=chinese.strip())


def _kill_process_tree(pid: int) -> None:
    """Windows 下 cmd /c 包装的 claude.cmd 超时后，cmd 死了 node 成孤儿——必须杀整棵树。"""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=10)
        else:
            os.kill(pid, 9)
    except OSError:
        pass


def _build_command(executable: str) -> list[str]:
    command = [executable, "-p", "--output-format", "text"]
    model = os.environ.get("BILISUB_ALIGN_MODEL", "haiku")  # 机械切分任务用快档，不跟全局 max 设置
    if model:
        command += ["--model", model]
    if executable.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", *command]
    return command


def _run(command: list[str], prompt: str, timeout: int) -> subprocess.CompletedProcess:
    """Popen+communicate：超时瞬间树还活着，taskkill /T 才杀得掉 node 孙进程。

    subprocess.run(timeout=...) 会先杀直接子进程(cmd 包装)再抛 TimeoutExpired，
    那时树根已死、孙进程已脱管——必须在抛出前对存活树根下 taskkill /F /T。
    """
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8",
    )
    try:
        stdout, stderr = process.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process.pid)
        raise
    return subprocess.CompletedProcess(process.args, process.returncode or 0,
                                       stdout=stdout or "", stderr=stderr or "")


def run_claude_align(prompt: str, timeout: int = ALIGN_TIMEOUT_SECONDS) -> str:
    """无头调用本机 claude CLI（stdin 进、stdout 出）；失败给可操作提示。

    超时杀整棵进程树；带 --model 快档失败时去掉该参数裸跑一次（兼容没配该模型别名的网关）。
    """
    executable = shutil.which("claude")
    if not executable:
        raise RuntimeError("未找到 claude 命令——一键排版需要本机已安装 Claude Code 并在 PATH 中")

    command = _build_command(executable)
    try:
        result = _run(command, prompt, timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"排版超时（>{timeout} 秒），已终止进程树，可重试，或改用「保存，交给 Claude 排版」") from exc
    except OSError as exc:
        raise RuntimeError(f"claude 命令启动失败：{exc}") from exc
    if (result.returncode != 0 or not (result.stdout or "").strip()) and "--model" in command:
        # 快档不被网关认识 → 去掉 --model 及其值，保留 cmd /c 包装裸跑一次
        retry_command = command[:command.index("--model")]
        try:
            result = _run(retry_command, prompt, timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"排版超时（>{timeout} 秒），已终止进程树，可重试，或改用「保存，交给 Claude 排版」") from exc
        except OSError as exc:
            raise RuntimeError(f"claude 命令启动失败：{exc}") from exc
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        detail = (result.stderr or "").strip().splitlines()
        hint = detail[-1] if detail else f"退出码 {result.returncode}"
        raise RuntimeError(f"claude 调用失败：{hint}")
    return output
