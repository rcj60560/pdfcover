"""Build a flat Cambridge IELTS audio library from downloaded archives.

Source files are never modified. The default uses NTFS hard links so the
2.5 GB library does not consume another 2.5 GB of disk space.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


DEFAULT_SOURCES = (
    Path(r"D:\夸克下载\听力音频"),
    Path(r"D:\夸克下载\剑雅19-21pdf+音频"),
)
DEFAULT_TARGET = Path(__file__).resolve().parent / "books"


def issue_number(name: str) -> int | None:
    for pattern in (r"【听力(\d+)】", r"剑桥?(\d+)", r"^(\d+)"):
        match = re.search(pattern, name)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 21:
                return value
    return None


def track_number(issue: int, path: Path) -> tuple[int, int | None]:
    text = "/".join(path.parts)
    test_match = re.search(r"(?:tests?|t)[ _.-]*(\d+)", text, re.IGNORECASE)

    if issue <= 3:
        if not test_match:
            raise ValueError(f"cannot find test number: {path}")
        return int(test_match.group(1)), None

    part_match = re.search(
        r"(?:section|secton|seciton|part|audio|p)[ _.-]*(\d+)",
        path.stem,
        re.IGNORECASE,
    )
    if test_match and not part_match:
        pair_match = re.search(
            r"(?:tests?|t)[ _.-]*(\d+)[ _.-]+(\d+)",
            path.stem,
            re.IGNORECASE,
        )
        if pair_match:
            return int(pair_match.group(1)), int(pair_match.group(2))

    if not test_match or not part_match:
        numeric_match = re.search(
            rf"(?:^|[^\d]){issue}[ _.-]+(\d+)[ _.-]+(\d+)(?:[^\d]|$)",
            path.stem,
        )
        if numeric_match:
            return int(numeric_match.group(1)), int(numeric_match.group(2))
        raise ValueError(f"cannot find test/part number: {path}")

    return int(test_match.group(1)), int(part_match.group(1))


def discover(sources: tuple[Path, ...]) -> dict[int, dict[str, Path]]:
    library: dict[int, dict[str, Path]] = {}
    for source in sources:
        if not source.is_dir():
            raise FileNotFoundError(source)
        for top_dir in source.iterdir():
            if not top_dir.is_dir():
                continue
            issue = issue_number(top_dir.name)
            if issue is None:
                continue
            for audio in top_dir.rglob("*"):
                if not audio.is_file() or audio.suffix.lower() != ".mp3":
                    continue
                test, part = track_number(issue, audio.relative_to(top_dir))
                name = f"T{test:02d}.mp3" if part is None else f"T{test:02d}-P{part:02d}.mp3"
                issue_tracks = library.setdefault(issue, {})
                if name in issue_tracks:
                    raise ValueError(
                        f"duplicate track for issue {issue}: {name}\n"
                        f"  {issue_tracks[name]}\n  {audio}"
                    )
                issue_tracks[name] = audio
    return library


def validate(library: dict[int, dict[str, Path]]) -> None:
    missing_issues = sorted(set(range(1, 22)) - set(library))
    if missing_issues:
        raise ValueError(f"missing issues: {missing_issues}")
    for issue in range(1, 22):
        expected = 4 if issue <= 3 else 16
        actual = len(library[issue])
        if actual != expected:
            raise ValueError(f"issue {issue}: expected {expected} tracks, found {actual}")


def materialize(library: dict[int, dict[str, Path]], target: Path, copy: bool) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for issue in range(1, 22):
        issue_dir = target / f"剑桥雅思{issue}"
        issue_dir.mkdir(exist_ok=True)
        expected_names = set(library[issue])
        for stale in issue_dir.iterdir():
            if stale.is_file() and stale.suffix.lower() == ".mp3" and stale.name not in expected_names:
                stale.unlink()
        for name, source in sorted(library[issue].items()):
            destination = issue_dir / name
            if destination.exists():
                try:
                    if os.path.samefile(source, destination):
                        continue
                except OSError:
                    pass
                destination.unlink()
            if copy:
                shutil.copy2(source, destination)
            else:
                try:
                    os.link(source, destination)
                except OSError as exc:
                    raise OSError(f"hard-link failed for {source}; rerun with --copy") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the 1-21 IELTS audio library")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--copy", action="store_true", help="copy files instead of hard-linking")
    args = parser.parse_args()

    library = discover(DEFAULT_SOURCES)
    validate(library)
    materialize(library, args.target, args.copy)
    total = sum(len(tracks) for tracks in library.values())
    mode = "copied" if args.copy else "hard-linked"
    print(f"{mode} {total} MP3 files into {args.target}")
    for issue in range(1, 22):
        print(f"  {issue:02d}: {len(library[issue])} tracks")


if __name__ == "__main__":
    main()
