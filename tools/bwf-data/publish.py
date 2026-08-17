"""校验 out/*.json 并发布到羽圈 App 仓库（git add + commit；push 需显式开启）"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).parent
OUT = ROOT / "out"


def load_config() -> dict:
    return tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["app"]


def validate(rankings: dict, schedule: dict) -> None:
    assert set(rankings.get("disciplines", {})) == {"ms", "ws", "md", "wd", "xd"}, "排名缺少单项"
    for k, d in rankings["disciplines"].items():
        assert len(d["entries"]) >= 40, f"{k} 行数不足 40"
    assert len(schedule.get("tournaments", [])) >= 20, "赛程站数不足 20"


def main(dry_run: bool = False, push: bool = False) -> None:
    rankings = json.loads((OUT / "rankings.json").read_text(encoding="utf-8"))
    schedule = json.loads((OUT / "schedule.json").read_text(encoding="utf-8"))
    validate(rankings, schedule)
    app = load_config()
    dest = Path(app["repo"]) / app["assets_dir"]
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("rankings.json", "schedule.json"):
        shutil.copy(OUT / name, dest / name)
        print(f"copy {name} -> {dest / name}")
    if dry_run:
        print("dry-run：不执行 git 提交")
        return
    repo = app["repo"]
    subprocess.run(["git", "-C", repo, "add", app["assets_dir"]], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", f"data: BWF 更新 {date.today().isoformat()}"], check=True)
    if push:
        subprocess.run(["git", "-C", repo, "push"], check=False)  # 无网/凭据问题不中断，下次 push 即可
    print("OK 已发布到 App 仓库")


if __name__ == "__main__":
    main()
