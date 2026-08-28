"""一键：抓排名+赛程 → 生成预览页 →（可选 --publish 发布到羽圈 App 仓库，另加 --push 才推送远端）"""
from __future__ import annotations

import argparse
from pathlib import Path

import preview_gen
import scrape_rankings
import scrape_schedule


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BWF 数据抓取/预览/发布")
    parser.add_argument("--publish", action="store_true", help="发布 JSON 到羽圈 App 仓库并 commit（push 需另加 --push）")
    parser.add_argument("--push", action="store_true", help="commit 后推送到远端（仅在 --publish 发布流程中生效）")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    scrape_rankings.main()
    scrape_schedule.main()
    preview_gen.main()
    print(f"浏览器打开查看: {Path(__file__).parent / 'out' / 'preview.html'}")
    if args.publish:
        import publish
        publish.main(push=args.push)


if __name__ == "__main__":
    main()
