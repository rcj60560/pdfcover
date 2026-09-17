"""剑桥雅思核心词汇 → 字幕 md 全流程。中间产物缓存于 tmp/cambridge_cache。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # tools/subtitle-viewer → import cambridge.*

from cambridge.align import align_turns, match_tracks
from cambridge.build_md import build_md
from cambridge.extract import extract_from_pdf
from cambridge.transcribe import transcribe_all

OCR_PDF = r"D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练_OCR.pdf"
AUDIO_DIR = r"D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练  音频"
CACHE = HERE.parents[2] / "tmp" / "cambridge_cache"
DEFAULT_OUT = Path(r"D:/Users/luocj/Ahuaxi/hcrs_devdocs/ielts/剑桥雅思核心词汇精讲精练")


def load_json(path: Path, producer):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    data = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理指定录音,如 1a")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry", action="store_true", help="只出报告,不写 md")
    args = ap.parse_args()

    recs = load_json(CACHE / "recordings.json", lambda: extract_from_pdf(OCR_PDF))
    tracks = transcribe_all(AUDIO_DIR, CACHE)
    mapping, no_rec, no_track = match_tracks(recs, tracks)
    (CACHE / "match.json").write_text(
        json.dumps({"mapping": mapping, "no_rec": no_rec, "no_track": no_track},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    units = json.loads((HERE / "units.json").read_text(encoding="utf-8"))

    report = []
    for rec in recs:
        if args.only and rec["id"] != args.only:
            continue
        rid = rec["id"]
        if rid not in mapping:
            report.append(f"SKIP {rid}: 无匹配 Track"); continue
        aligned = align_turns(rec["turns"], tracks[mapping[rid]])
        tfile = HERE / "translations" / f"{rid}.json"
        zh = ({int(k): v for k, v in json.loads(tfile.read_text(encoding="utf-8")).items()}
              if tfile.is_file() else {})
        unit = f"{rid.rstrip('abcdefghijklmnopqrstuvwxyz')} {units.get(rid.rstrip('abcdefghijklmnopqrstuvwxyz'), '')}".strip()
        low = sum(1 for t in aligned if t["conf"] < 0.5)
        report.append(f"{rid} → {mapping[rid]}: {len(aligned)} 段, 低置信 {low}, 中文 {len(zh)}/{len(aligned)}")
        if args.dry:
            continue
        md = build_md(rid, unit, aligned, mapping[rid], zh)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"Recording {rid}｜Unit {unit}.md").write_text(md, encoding="utf-8")

    print("\n".join(report) or "无录音")
    print("未匹配录音:", " ".join(no_rec) or "-", "| 未匹配 Track:", " ".join(no_track) or "-")


if __name__ == "__main__":
    main()
