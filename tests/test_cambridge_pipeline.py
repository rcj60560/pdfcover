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


def test_words_of_normalizes_unicode_punctuation():
    from cambridge.align import words_of
    assert words_of("I can't – STOP!") == ["i", "can't", "stop"]


def test_align_turns_matches_and_interpolates_unmatched_run():
    from cambridge.align import align_turns

    turns = [
        {"label": "A", "text": "alpha"},
        {"label": "B", "text": "bravo charlie"},
        {"label": "C", "text": "delta echo foxtrot"},
        {"label": "D", "text": "omega"},
    ]
    words = [
        {"w": "alpha", "s": 1.0, "e": 2.0},
        {"w": "omega", "s": 10.0, "e": 11.0},
    ]

    out = align_turns(turns, words)
    assert (out[0]["start"], out[0]["end"], out[0]["conf"]) == (1.0, 2.0, 1.0)
    assert (out[1]["start"], out[1]["end"], out[1]["conf"]) == (2.0, 5.2, 0.0)
    assert (out[2]["start"], out[2]["end"], out[2]["conf"]) == (5.2, 10.0, 0.0)
    assert (out[3]["start"], out[3]["end"], out[3]["conf"]) == (10.0, 11.0, 1.0)


def test_align_turns_whole_track_interpolation_and_empty_audio():
    from cambridge.align import align_turns

    turns = [
        {"label": "A", "text": "one"},
        {"label": "B", "text": "two three"},
    ]
    out = align_turns(turns, [
        {"w": "unrelated", "s": 2.0, "e": 5.0},
    ])
    assert (out[0]["start"], out[0]["end"]) == (0.0, 5 / 3)
    assert (out[1]["start"], out[1]["end"]) == (5 / 3, 5.0)
    assert all(item["conf"] == 0.0 for item in out)

    empty = align_turns(turns, [])
    assert all(item["start"] == item["end"] == 0.0 for item in empty)


MERGED_HEADING_PAGES = [
    # p166:5c 词表结尾连排 6a 独白(OCR 文本层漏了 “Recording 6a” 标题)
    "Recording 5c\n"
    "academic, assignment, controversy, research (n), thesis, theory, theoretical\n"
    "I'm a French teacher, but I remember when I first started to learn\n"
    "the language I really struggled with it.\n",
    "Recording 6b\n"
    "Speaker A: Now listen again and answer questions one to five.\n",
    # p167:8a 说话人段落连排 8b 讲座(漏了 “Recording 8b” 标题)
    "Recording 8a\n"
    "Speaker 3: I own about 12 watches and clocks, but none of them show the\n"
    "right time. Welcome once again to 'Introduction to dentistry' and in\n"
    "today's lecture we'll be looking at the history of dentistry.\n",
    "Recording 9a\n"
    "Speaker A: Hello there.\n",
]


def test_inject_missing_headings_splits_merged_recordings():
    from cambridge.extract import inject_missing_headings, parse_scripts

    recs = parse_scripts(inject_missing_headings(MERGED_HEADING_PAGES))
    assert [r["id"] for r in recs] == ["5c", "6a", "6b", "8a", "8b", "9a"]
    # 5c 词表独立成条,不再吸入 6a 独白
    assert recs[0]["turns"] == [{"label": "",
        "text": "academic, assignment, controversy, research (n), thesis, "
                "theory, theoretical I'm a"}]
    # 6a 独白内容完整
    assert recs[1]["turns"] == [{"label": "",
        "text": "French teacher, but I remember when I first started to learn "
                "the language I really struggled with it."}]
    # 8a 说话人段落止于原句末
    assert recs[3]["turns"] == [{"label": "Speaker 3",
        "text": "I own about 12 watches and clocks, but none of them show the right time."}]
    # 8b 讲座独立成条、内容完整
    assert recs[4]["turns"] == [{"label": "",
        "text": "Welcome once again to 'Introduction to dentistry' and in today's "
                "lecture we'll be looking at the history of dentistry."}]


def test_inject_missing_headings_raises_when_marker_count_differs():
    import pytest
    from cambridge.extract import inject_missing_headings

    duplicated = ["Recording 5c\n"
                  "The French teacher, but meets another French teacher, but here.\n"]
    with pytest.raises(ValueError):
        inject_missing_headings(duplicated)

    absent = ["Recording 1a\nSpeaker A: Nothing to see.\n"]  # 换书:标志缺失
    with pytest.raises(ValueError):
        inject_missing_headings(absent)


def test_match_tracks_accepts_similarity_at_threshold():
    from cambridge.align import match_tracks

    recordings = [{"id": "r", "turns": [{"label": "", "text": "one two"}]}]
    tracks = {"Track.mp3": [{"w": word, "s": i, "e": i + 1}
                            for i, word in enumerate("one three".split())]}
    mapping, no_recording, no_track = match_tracks(recordings, tracks)
    assert mapping == {"r": "Track.mp3"}
    assert no_recording == []
    assert no_track == []


def test_match_tracks_skips_unspoken_leading_instructions():
    """4b 场景:脚本开头 26 词指令音频里未朗读,需前缀偏移后才能对上。"""
    from cambridge.align import match_tracks

    instructions = ("You will hear a woman talking on radio about spare activities "
                    "occupying younger minds during vacation time before beginning "
                    "listen carefully now very good luck everyone").split()
    real = "The school holidays are fast approaching and I'm sure all of you".split()
    assert len(instructions) == 26 and len(real) == 12
    recordings = [{"id": "4b", "turns": [
        {"label": "Narrator", "text": " ".join(instructions + real)}]}]
    tracks = {"Track12.mp3": [{"w": word, "s": i, "e": i + 1}
                              for i, word in enumerate(real)]}
    mapping, no_recording, no_track = match_tracks(recordings, tracks)
    assert mapping == {"4b": "Track12.mp3"}
    assert no_recording == []
    assert no_track == []


def test_fmt_ts():
    from cambridge.build_md import fmt_ts

    assert fmt_ts(83.4) == "1:23"
    assert fmt_ts(3723) == "1:02:03"


def test_build_md_formats_turns_with_timestamps_and_translation():
    from cambridge.build_md import build_md
    from subtitle_lib import has_timestamps

    turns = [
        {"label": "Speaker A", "text": "Hello world.", "start": 0.0, "end": 2.0, "conf": 1.0},
        {"label": "Speaker B", "text": "Good night.", "start": 5.0, "end": 6.0, "conf": 1.0},
    ]
    md = build_md("1a", "1 Family", turns, "Track01.mp3", {0: "你好,世界。", 1: "晚安。"})

    assert has_timestamps(md)
    assert "`0:00 → 0:05`" in md
    assert "`0:05 → 0:06`" in md
    assert "# 剑桥雅思核心词汇精讲精练 Recording 1a｜Unit 1 Family" in md
    assert "中文 `精翻`" in md
    assert "**Speaker A: Hello world.**" in md
    assert "你好,世界。" in md
    assert "Track01.mp3" in md


def test_md_filename_uses_fullwidth_separator():
    from cambridge.build_md import md_filename

    assert md_filename("1a", "1 Family") == "Recording 1a｜Unit 1 Family.md"
    assert "—" not in md_filename("22b", "22 Colour")  # 半角破折号不再用作分隔
