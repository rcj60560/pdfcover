"""剑桥词汇管线纯逻辑测试。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "subtitle-viewer"
sys.path.insert(0, str(TOOL))

PAGES = [
    "Recording 1a\n"
    "Speaker A: On Mondays | often talk about movies.\n"
    "Speaker B: My parents are both teachers.\n",
    "Recording 1b\n"
    "Teacher: Tell me about your family.\n"
    "Student: Well, my immediate family is small!\n"
    "Recording 1c\n"           # 无说话人 → 整段 narration
    "You will hear two people talking about family.\n",
]

def test_clean_line():
    from cambridge.extract import clean_line
    assert clean_line("| often can’t stop") == "I often can't stop"
    assert clean_line("small! and fun") == "small! and fun"   # 紧贴单词的 ! 不是 I
    assert clean_line("abie   able") == "abie able"

def test_parse_scripts():
    from cambridge.extract import parse_scripts
    recs = parse_scripts(PAGES)
    assert [r["id"] for r in recs] == ["1a", "1b", "1c"]
    assert recs[0]["turns"][0] == {"label": "Speaker A",
        "text": "On Mondays I often talk about movies."}
    assert recs[1]["turns"] == [
        {"label": "Teacher", "text": "Tell me about your family."},
        {"label": "Student", "text": "Well, my immediate family is small!"},
    ]
    assert recs[2]["turns"] == [{"label": "",
        "text": "You will hear two people talking about family."}]
