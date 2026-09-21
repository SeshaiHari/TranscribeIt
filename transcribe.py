#!/usr/bin/env python3
"""Transcribe a video/audio file to txt, srt or vtt using faster-whisper (free, offline)."""
import argparse
import sys
from pathlib import Path

from transcribe_core import DEVICE_LABELS, FORMATS, format_segments, transcribe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", type=Path, help="path to video or audio file")
    p.add_argument("--model", default="small",
                   help="tiny, base, small, medium, large-v3 (default: small)")
    p.add_argument("--language", default=None, help="e.g. en, hi (default: auto-detect)")
    p.add_argument("--format", choices=FORMATS, default="txt")
    p.add_argument("--out", type=Path, default=None,
                   help="output file (default: next to the video)")
    args = p.parse_args()

    if not args.video.is_file():
        sys.exit(f"File not found: {args.video}")
    out = args.out or args.video.with_suffix(f".{args.format}")
    out.parent.mkdir(parents=True, exist_ok=True)

    def info(i):
        conf = f" (p={i.language_probability:.2f})" if i.language_probability else ""
        print(f"Language: {i.language}{conf}, duration: {i.duration:.0f}s", file=sys.stderr)

    def device(name):
        print(f"Device: {DEVICE_LABELS[name]}", file=sys.stderr)

    def progress(item, total):
        pct = min(100, int(item["end"] / total * 100)) if total else 0
        print(f"\r[{pct:3}%] {item['text'][:60]:<60}", end="", file=sys.stderr, flush=True)

    try:
        segments = transcribe(args.video, args.model, args.language, info, progress, device)
    except RuntimeError as e:
        sys.exit(str(e))
    print(file=sys.stderr)
    out.write_text(format_segments(segments, args.format), encoding="utf-8")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
