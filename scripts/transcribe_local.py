#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from opencc import OpenCC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local faster-whisper runner")
    parser.add_argument("audio_path")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--language", default="")
    parser.add_argument("--vad", action="store_true")
    parser.add_argument("--no-simplify", action="store_true", help="Disable Traditional-to-Simplified post-processing")
    parser.add_argument("-j", "--json-output", action="store_true")
    parser.add_argument("-o", "--output", required=True)
    return parser


def maybe_simplify(text: str, language: str, disable: bool) -> str:
    if disable:
        return text
    if language and not language.lower().startswith("zh"):
        return text
    return OpenCC("t2s").convert(text)


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    device = "cpu"
    compute_type = "int8"
    if os.environ.get("CT2_USE_MPS", "").lower() in {"1", "true", "yes"}:
        device = "auto"

    model = WhisperModel(args.model, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        args.audio_path,
        beam_size=max(1, args.beam_size),
        language=args.language or None,
        vad_filter=args.vad,
    )

    rows = []
    text_parts = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        text = maybe_simplify(text, args.language or getattr(info, "language", "") or "", args.no_simplify)
        text_parts.append(text)
        rows.append({"start": seg.start, "end": seg.end, "text": text})

    payload = {
        "text": "\n".join(text_parts).strip(),
        "segments": rows,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
