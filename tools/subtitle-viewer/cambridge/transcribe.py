"""faster-whisper word-level transcription with JSON caching."""
from __future__ import annotations

import json
from pathlib import Path


_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _MODEL


def transcribe_all(audio_dir: str, cache_dir: str) -> dict[str, list[dict]]:
    """Transcribe all Track*.mp3 files, caching word timestamps per track."""
    audio = sorted(Path(audio_dir).glob("Track*.mp3"))
    if not audio:
        raise SystemExit(f"audio directory has no Track*.mp3: {audio_dir}")

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out: dict[str, list[dict]] = {}
    for mp3 in audio:
        cache_json = cache / (mp3.stem + ".words.json")
        if cache_json.is_file():
            out[mp3.name] = json.loads(cache_json.read_text(encoding="utf-8"))
            print(f"[cache] {mp3.name}")
            continue

        print(f"[whisper] {mp3.name} ...")
        segments, _info = _model().transcribe(
            str(mp3), language="en", word_timestamps=True
        )
        words = [
            {"w": word.word.strip(), "s": round(word.start, 2), "e": round(word.end, 2)}
            for segment in segments
            for word in (segment.words or [])
        ]
        cache_json.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        out[mp3.name] = words

    return out
