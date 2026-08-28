"""新世纪走遍美国 xls -> units.json。

读 xls 的「合集」sheet，切分单元并归一化编号（U004->U04、无标题纯数字头
U0102 = U01 第 2 幕，并入 U01），台词行收集为 {en, cn} 列表。
中间产物，供生成 IELTS 话题用；不参与 launcher。

用法：python scripts/extract_units.py [xls路径] [输出json路径]
"""
import json
import re
import sys
from pathlib import Path

import xlrd

_HEADER = re.compile(r"^U(\d+)\s*(.*)$")


def parse_header(text):
    """识别单元头行。返回 {num,id,title,act}；普通台词行返回 None。

    - "U01 Rebecca's Dream" -> U01 第 1 幕
    - "U004 Celebrations"   -> U04（去前导零）
    - "U0102"               -> U01 第 2 幕（U01+02，无标题的分幕头）
    """
    m = _HEADER.match(text.strip())
    if not m:
        return None
    digits, title = m.group(1), m.group(2).strip()
    if title:
        num, act = int(digits), 1
    elif len(digits) >= 4:            # U0102 / U0103：前 2 位单元号 + 后 2 位幕号
        num, act = int(digits[:2]), int(digits[2:])
    else:
        num, act = int(digits), 1
    return {"num": num, "id": f"U{num:02d}", "title": title or None, "act": act}


def extract_units(sheet):
    """xlrd sheet（鸭子类型：name/nrows/cell_value）-> {"units":[...], "missing":[...]}。"""
    units, by_num, cur = [], {}, None
    for r in range(sheet.nrows):
        en = str(sheet.cell_value(r, 0)).strip()
        cn = str(sheet.cell_value(r, 1)).strip()
        header = parse_header(en)
        if header:
            if header["num"] not in by_num:
                unit = {"id": header["id"], "num": header["num"],
                        "title": header["title"], "dialogue": []}
                units.append(unit)
                by_num[header["num"]] = unit
            elif header["title"] and not by_num[header["num"]]["title"]:
                by_num[header["num"]]["title"] = header["title"]
            cur = by_num[header["num"]]        # 分幕头：后续台词仍归同一单元
            continue
        if not en and not cn:
            continue
        if cur:                                # 首个头之前的行丢弃
            cur["dialogue"].append({"en": en, "cn": cn})
    units.sort(key=lambda u: u["num"])
    nums = {u["num"] for u in units}
    missing = [f"U{n:02d}" for n in range(1, max(nums) + 1) if n not in nums]
    return {"units": units, "missing": missing}


def main(argv):
    xls = Path(argv[1]) if len(argv) > 1 else Path(__file__).parent / "新世纪走遍美国-中英文台词.xls"
    out = Path(argv[2]) if len(argv) > 2 else Path(__file__).parent / "out" / "units.json"
    sheet = xlrd.open_workbook(xls).sheet_by_name("合集")
    data = extract_units(sheet)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = sum(len(u["dialogue"]) for u in data["units"])
    print(f"{len(data['units'])} units, {lines} lines -> {out}")
    if data["missing"]:
        print("missing:", ", ".join(data["missing"]))


if __name__ == "__main__":
    main(sys.argv)
