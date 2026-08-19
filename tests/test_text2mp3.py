"""text2mp3 纯逻辑单测（不触网、不装 edge-tts 也能跑）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "text2mp3"))
import tts_core as core  # noqa: E402


def test_sanitize_removes_illegal_chars():
    name = core.sanitize_filename('话题1: 为什么/要学英语?')
    for ch in '\\/:*?"<>|':
        assert ch not in name
    assert "话题1" in name and "要学英语" in name   # 词内无非法字符则保持完整


def test_sanitize_empty_falls_back_to_timestamp():
    assert core.sanitize_filename("   ").startswith("tts-")


def test_format_rate_sign_and_clamp():
    assert core.format_rate(0) == "+0%"
    assert core.format_rate(-15) == "-15%"
    assert core.format_rate(20) == "+20%"
    assert core.format_rate(-99) == "-50%"    # 下限
    assert core.format_rate(500) == "+100%"   # 上限


def test_format_pitch_sign_and_clamp():
    assert core.format_pitch(0) == "+0Hz"
    assert core.format_pitch(-5) == "-5Hz"
    assert core.format_pitch(10) == "+10Hz"
    assert core.format_pitch(-99) == "-50Hz"  # 下限
    assert core.format_pitch(500) == "+50Hz"  # 上限


def test_voices_table_sane():
    assert len(set(core.VOICES.values())) == len(core.VOICES)   # 无重复 ID
    assert core.DEFAULT_VOICE in core.VOICES.values()
    assert any("Ava" in vid for vid in core.VOICES.values())    # 新一代语音在列


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG_PATH", tmp_path / "config.json")
    core.save_config("en-US-AriaNeural", -10, -5, r"C:\somewhere")
    assert core.load_config() == {
        "voice": "en-US-AriaNeural", "rate": -10, "pitch": -5, "out_dir": r"C:\somewhere",
    }


def test_load_config_default_when_missing_or_broken(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG_PATH", tmp_path / "none.json")
    cfg = core.load_config()
    assert cfg["voice"] == core.DEFAULT_VOICE
    assert cfg["out_dir"] == core.DEFAULT_OUT_DIR

    (tmp_path / "broken.json").write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(core, "CONFIG_PATH", tmp_path / "broken.json")
    assert core.load_config()["rate"] == 0


def test_resolve_output_path_cleans_and_mkdir(tmp_path):
    p = core.resolve_output_path(str(tmp_path / "new" / "dir"), "话 题:1")
    assert p.parent.is_dir()                      # 目录自动创建
    assert p.suffix == ".mp3"
    assert p.name == "话 题 1.mp3"                 # 非法字符→空格，空白折叠


def test_manifest_discovers_text2mp3():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {t.slug: t for t in load_tools(Path(__file__).parents[1] / "tools")}
    tool = tools["text2mp3"]
    assert tool.status == "ready"
    assert tool.port == 8300
    assert tool.name == "文本转语音 MP3"


def _ev(text, offset_100ns, dur_100ns):
    return {"type": "WordBoundary", "text": text, "offset": offset_100ns, "duration": dur_100ns}


def test_split_sentences_text():
    text = "To me, English is a bridge. It's magical! Isn't it?"
    assert core.split_sentences_text(text) == [
        "To me, English is a bridge.", "It's magical!", "Isn't it?",
    ]
    assert core.split_sentences_text("  ") == []


def test_build_timeline_units_and_sentences():
    events = [
        _ev("To", 0, 2_100_000),           # s=0ms d=210ms
        _ev("me,", 240_000, 180_000),      # s=24ms d=18ms
        _ev("world.", 500_000, 300_000),   # s=50ms d=30ms
    ]
    tl = core.build_timeline(events, text="To me, world.",
                             voice="v1", rate="-10%", pitch="+0Hz", translation="译")
    assert tl["words"] == [
        {"t": "To", "s": 0, "d": 210},
        {"t": "me,", "s": 24, "d": 18},
        {"t": "world.", "s": 50, "d": 30},
    ]
    # 一句（token 数 3 = 词数 3），覆盖全部词
    assert len(tl["sentences"]) == 1
    s = tl["sentences"][0]
    assert (s["i"], s["j"]) == (0, 2)
    assert s["start"] == 0 and s["end"] == 80   # 50+30
    assert tl["translation"] == "译" and tl["voice"] == "v1"


def test_build_timeline_multi_sentence_by_token_count():
    text = "I jump. You run fast!"
    # 原文句子 token 数：[2, 3]
    events = [
        _ev("I", 0, 100_000), _ev("jump.", 100_000, 100_000),
        _ev("You", 300_000, 100_000), _ev("run", 450_000, 100_000), _ev("fast!", 600_000, 150_000),
    ]
    tl = core.build_timeline(events, text=text)
    assert [(s["i"], s["j"]) for s in tl["sentences"]] == [(0, 1), (2, 4)]
    assert tl["sentences"][0]["end"] == 20        # 10+10
    assert tl["sentences"][1]["start"] == 30


def test_build_timeline_empty_and_tail_merge():
    assert core.build_timeline([], text="x")["words"] == []
    assert core.build_timeline([], text="x")["sentences"] == []
    # 尾部剩余词并入最后一句（token 数对不上时）
    events = [_ev("a", 0, 100_000), _ev("b", 100_000, 100_000), _ev("c", 200_000, 100_000)]
    tl = core.build_timeline(events, text="a. b.")   # 句子 token 数 [1,1]，第三个词多出来
    assert (tl["sentences"][-1]["i"], tl["sentences"][-1]["j"]) == (1, 2)


def test_timeline_path_and_write(tmp_path):
    mp3 = tmp_path / "话题1-试.mp3"
    p = core.timeline_path(mp3)
    assert p.name == "话题1-试.json"
    out = core.write_timeline(mp3, {"words": [], "sentences": [], "translation": ""})
    assert out == p and p.exists()


def test_stream_sink_collects_and_writes(tmp_path):
    mp3 = tmp_path / "a.mp3"
    sink = core.StreamSink(mp3)
    for chunk in [
        {"type": "audio", "data": b"\xff\xf3x"},
        {"type": "WordBoundary", "text": "Hi", "offset": 0, "duration": 100_000},
        {"type": "audio", "data": b"y"},
        {"type": "SentenceBoundary", "offset": 0, "duration": 0, "text": "Hi"},
    ]:
        sink.feed(chunk)
    sink.close()
    assert mp3.read_bytes() == b"\xff\xf3xy"
    assert sink.events == [{"type": "WordBoundary", "text": "Hi", "offset": 0, "duration": 100_000}]


def test_synthesize_failure_cleans_pair(tmp_path, monkeypatch):
    """合成中途失败：截断 mp3 与同名旧 json 都不得留在盘上（离线 fake edge_tts）。"""
    import asyncio
    import types

    class _Comm:
        def __init__(self, *a, **k):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"\xff\xf3x"}
            raise RuntimeError("net down")

    fake = types.ModuleType("edge_tts")
    fake.Communicate = _Comm
    monkeypatch.setitem(sys.modules, "edge_tts", fake)

    mp3 = tmp_path / "a.mp3"
    stale = core.timeline_path(mp3)
    stale.write_text("{}", encoding="utf-8")   # 模拟上一次成功运行留下的旧 json
    import pytest
    with pytest.raises(RuntimeError):
        asyncio.run(core.synthesize("hi", "v", "+0%", "+0Hz", mp3))
    assert not mp3.exists() and not stale.exists()
