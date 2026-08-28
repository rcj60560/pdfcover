"""extract_units：xls「合集」sheet -> 单元归一化 + 台词切分（伪 sheet fixture，不依赖真实 xls）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from extract_units import extract_units, parse_header  # noqa: E402


class FakeSheet:
    """xlrd sheet 的鸭子类型：只需 name/nrows/cell_value。"""

    def __init__(self, rows, name="合集"):
        self.name = name
        self.rows = rows

    @property
    def nrows(self):
        return len(self.rows)

    def cell_value(self, r, c):
        return self.rows[r][c] if c < len(self.rows[r]) else ""


def test_parse_header_variants():
    assert parse_header("U01 Rebecca’s Dream") == {
        "num": 1, "id": "U01", "title": "Rebecca’s Dream", "act": 1}
    assert parse_header("U004 Celebrations") == {
        "num": 4, "id": "U04", "title": "Celebrations", "act": 1}
    assert parse_header("U16 First Day of Class") == {
        "num": 16, "id": "U16", "title": "First Day of Class", "act": 1}
    # 无标题的纯数字头 = 同单元的分幕（U01 第 2/3 幕）
    assert parse_header("U0102") == {
        "num": 1, "id": "U01", "title": None, "act": 2}
    assert parse_header("U0103") == {
        "num": 1, "id": "U01", "title": None, "act": 3}
    # 非单元头（普通台词行）
    assert parse_header("Hello there") is None
    assert parse_header("") is None


def test_extract_splits_units_and_merges_acts():
    sheet = FakeSheet([
        ["U01 Rebecca’s Dream", ""],
        ["No!", "不。"],
        ["Yes!", "是。"],
        ["U0102", ""],
        ["I have to go.", "我要走了。"],
        ["U02 Differences", ""],
        ["Where are you going?", "你去哪？"],
    ])
    out = extract_units(sheet)
    assert len(out["units"]) == 2
    u01 = out["units"][0]
    assert u01["id"] == "U01" and u01["num"] == 1
    assert u01["title"] == "Rebecca’s Dream"
    # 三行台词按出现顺序并入 U01（分幕头本身不是台词）
    assert u01["dialogue"] == [
        {"en": "No!", "cn": "不。"},
        {"en": "Yes!", "cn": "是。"},
        {"en": "I have to go.", "cn": "我要走了。"},
    ]
    assert out["units"][1]["id"] == "U02"
    assert out["units"][1]["dialogue"] == [
        {"en": "Where are you going?", "cn": "你去哪？"}]


def test_extract_normalizes_leading_zero_ids():
    sheet = FakeSheet([
        ["U004 Celebrations", ""],
        ["Happy birthday!", "生日快乐！"],
    ])
    out = extract_units(sheet)
    assert out["units"][0]["id"] == "U04"
    assert out["units"][0]["num"] == 4


def test_extract_reports_missing_units():
    sheet = FakeSheet([
        ["U01 A", ""], ["hi", "嗨"],
        ["U04 D", ""], ["yo", "哟"],
    ])
    out = extract_units(sheet)
    assert out["missing"] == ["U02", "U03"]


def test_extract_skips_empty_rows():
    sheet = FakeSheet([
        ["U01 A", ""],
        ["", ""],
        ["real line", "真台词"],
        ["   ", "  "],
    ])
    out = extract_units(sheet)
    assert out["units"][0]["dialogue"] == [
        {"en": "real line", "cn": "真台词"}]
