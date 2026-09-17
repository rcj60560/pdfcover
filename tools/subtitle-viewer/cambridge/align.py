"""Align Cambridge script turns with Whisper word timestamps."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_word(w: str) -> str:
    """Return the comparable form of one script or transcript word."""
    value = unicodedata.normalize("NFKC", w)
    value = value.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"[^a-z0-9']", "", value.lower())


def words_of(text: str) -> list[str]:
    return [word for token in text.split() if (word := normalize_word(token))]


def _sim(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


# 录音开头可能含音频里未朗读的练习指令(如 4b 前 26 词),对录音头做
# 有界前缀偏移:依次跳过 0..HEAD_OFFSET_LIMIT 词再与 Track 头比较。
HEAD_OFFSET_LIMIT = 30


def _head_similarity(recording_words: list[str], track_words: list[str]) -> float:
    """Best similarity over bounded prefix offsets of the recording head."""
    best = 0.0
    for offset in range(min(HEAD_OFFSET_LIMIT, len(recording_words)) + 1):
        best = max(best, _sim(recording_words[offset:], track_words))
    return best


def _interpolate_run(out: list[dict], counts: list[int], first: int, last: int,
                     start: float, end: float) -> None:
    """Assign one consecutive unmatched turn run by script word counts."""
    weights = counts[first:last + 1]
    total = sum(weights)
    if total == 0:
        weights = [1] * len(weights)
        total = len(weights)
    span = max(0.0, end - start)
    cursor = start
    for offset, weight in enumerate(weights):
        boundary = start + span * sum(weights[:offset + 1]) / total
        out[first + offset].update(start=cursor, end=boundary, conf=0.0)
        cursor = boundary


def align_turns(turns: list[dict], w_words: list[dict]) -> list[dict]:
    script: list[tuple[str, int]] = []
    counts: list[int] = []
    for turn_index, turn in enumerate(turns):
        turn_words = words_of(turn["text"])
        counts.append(len(turn_words))
        script.extend((word, turn_index) for word in turn_words)

    whisper = [normalize_word(word["w"]) for word in w_words]
    matcher = SequenceMatcher(
        None, [word for word, _ in script], whisper, autojunk=False
    )
    hits: list[list[dict]] = [[] for _ in turns]
    for tag, script_start, script_end, word_start, word_end in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(script_end - script_start):
            turn_index = script[script_start + offset][1]
            hits[turn_index].append(w_words[word_start + offset])

    output: list[dict] = []
    for turn, words in zip(turns, hits):
        output.append({
            **turn,
            "start": min((word["s"] for word in words), default=None),
            "end": max((word["e"] for word in words), default=None),
            "conf": round(len(words) / counts[len(output)], 2)
            if counts[len(output)] else 0.0,
        })

    duration = max((float(word["e"]) for word in w_words), default=0.0)
    index = 0
    while index < len(output):
        if output[index]["start"] is not None:
            index += 1
            continue
        first = index
        while index + 1 < len(output) and output[index + 1]["start"] is None:
            index += 1
        last = index
        previous_end = next(
            (output[position]["end"] for position in range(first - 1, -1, -1)
             if output[position]["start"] is not None),
            0.0,
        )
        next_start = next(
            (output[position]["start"] for position in range(last + 1, len(output))
             if output[position]["start"] is not None),
            duration,
        )
        _interpolate_run(output, counts, first, last, previous_end, next_start)
        index += 1

    return output


def match_tracks(recordings: list[dict], tracks: dict[str, list[dict]],
                 threshold: float = 0.5) -> tuple[dict[str, str], list[str], list[str]]:
    recording_heads = {
        recording["id"]: words_of(" ".join(
            turn["text"] for turn in recording["turns"][:2]
        ))[:40]
        for recording in recordings
    }
    track_heads = {
        name: [normalize_word(word["w"]) for word in words][:60]
        for name, words in tracks.items()
    }
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for recording_id, recording_words in sorted(
        recording_heads.items(), key=lambda item: -len(item[1])
    ):
        best_name = None
        best_score = threshold
        for name, track_words in track_heads.items():
            if name in used:
                continue
            score = _head_similarity(recording_words, track_words)
            if score >= best_score:
                best_name, best_score = name, score
        if best_name is not None:
            mapping[recording_id] = best_name
            used.add(best_name)
    unmatched_recordings = [rid for rid in recording_heads if rid not in mapping]
    unmatched_tracks = [name for name in track_heads if name not in used]
    return mapping, unmatched_recordings, unmatched_tracks
