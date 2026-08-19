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
