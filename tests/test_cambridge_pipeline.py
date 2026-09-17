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

NOCOLON_PAGES = [
    "Recording 7a\n"            # 无冒号 A–J 枚举;run 后附录/Key 全部丢弃
    "A Leading environmentalists are concerned about warming.\n"
    "B Scientists have shown that fish may be beneficial.\n"
    "C Satellites have recently sent back new data from Mars.\n"
    "\n"
    "APPENDIX\n"
    "adolescence /x/\n"
    "Key: | = left, c = centre.\n",
    "Recording 8a\n"            # 带数字的说话人标签不残留
    "Speaker 1: Not really, | think so.\n"
    "Speaker 2: For me there is only one choice.\n",
    "Recording 9a\n"            # credits 标签出现即截断
    "Speaker A: Hello there.\n"
    "Key: | = left, c = centre, r = right.\n"
    "Picture research: Hilary Luckcock\n",
    "Recording 10a\n"           # 保守门:孤立 “A …” 行不切 turn
    "A man and a woman are talking about weather.\n"
    "They will discuss the family.\n",
]

def test_parse_scripts_no_colon_and_credits():
    from cambridge.extract import parse_scripts
    recs = parse_scripts(NOCOLON_PAGES)
    assert [r["id"] for r in recs] == ["7a", "8a", "9a", "10a"]
    assert recs[0]["turns"] == [
        {"label": "A", "text": "Leading environmentalists are concerned about warming."},
        {"label": "B", "text": "Scientists have shown that fish may be beneficial."},
        {"label": "C", "text": "Satellites have recently sent back new data from Mars."},
    ]
    assert recs[1]["turns"] == [
        {"label": "Speaker 1", "text": "Not really, I think so."},
        {"label": "Speaker 2", "text": "For me there is only one choice."},
    ]
    assert recs[2]["turns"] == [{"label": "Speaker A", "text": "Hello there."}]
    assert recs[3]["turns"] == [{"label": "",
        "text": "A man and a woman are talking about weather. They will discuss the family."}]
