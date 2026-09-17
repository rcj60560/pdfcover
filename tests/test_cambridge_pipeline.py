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


def test_match_tracks_accepts_similarity_at_threshold():
    from cambridge.align import match_tracks

    recordings = [{"id": "r", "turns": [{"label": "", "text": "one two"}]}]
    tracks = {"Track.mp3": [{"w": word, "s": i, "e": i + 1}
                            for i, word in enumerate("one three".split())]}
    mapping, no_recording, no_track = match_tracks(recordings, tracks)
    assert mapping == {"r": "Track.mp3"}
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
    assert "**Speaker A: Hello world.**" in md
    assert "你好,世界。" in md
    assert "Track01.mp3" in md
