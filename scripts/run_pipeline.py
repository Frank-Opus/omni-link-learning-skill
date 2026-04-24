#!/usr/bin/env python3
"""
Default pipeline:
1. Fetch source content / transcript
2. Generate deep analysis report

Optional:
3. Generate study plan
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def load_manifest(outdir: Path) -> dict:
    manifest_path = outdir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {outdir}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def choose_analysis_input(manifest: dict) -> Path:
    files = manifest.get("files") or {}
    transcript = files.get("transcript")
    if transcript:
        path = Path(transcript)
        if path.exists() and path.stat().st_size > 0:
            return path

    source_read = files.get("source_read")
    if source_read:
        path = Path(source_read)
        if path.exists() and path.stat().st_size > 0:
            return path

    raise FileNotFoundError("Neither transcript nor source_read is available for analysis.")


def choose_title(manifest: dict, outdir: Path) -> str:
    files = manifest.get("files") or {}
    for key in ("platform_meta",):
        path_str = files.get(key)
        if not path_str:
            continue
        path = Path(path_str)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                title = data.get("title")
                if title:
                    return str(title)
            except Exception:
                pass

    source = manifest.get("input") or "Untitled Source"
    return str(source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fetch + report pipeline, with optional study plan.")
    parser.add_argument("--input", required=True, help="URL, topic, or x-bookmarks query")
    parser.add_argument("--outdir", default="./omni_learning_output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retry", type=int, default=2)
    parser.add_argument("--asr-fallback", action="store_true")
    parser.add_argument("--asr-model", default="large-v3-turbo")
    parser.add_argument("--asr-language", default="zh")
    parser.add_argument("--asr-beam-size", type=int, default=5)
    parser.add_argument(
        "--with-study-plan",
        action="store_true",
        help="Also generate study_plan.md. Disabled by default so the main output stays focused on the full report.",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    fetch_cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "fetch_source.py"),
        "--input",
        args.input,
        "--outdir",
        str(outdir),
        "--timeout",
        str(args.timeout),
        "--retry",
        str(args.retry),
        "--asr-model",
        args.asr_model,
        "--asr-language",
        args.asr_language,
        "--asr-beam-size",
        str(args.asr_beam_size),
    ]
    if args.asr_fallback:
        fetch_cmd.append("--asr-fallback")

    run(fetch_cmd)

    manifest = load_manifest(outdir)
    analysis_input = choose_analysis_input(manifest)
    title = choose_title(manifest, outdir)

    analysis_output = outdir / "analysis_report.md"
    run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "deep_analyzer.py"),
            "--input",
            str(analysis_input),
            "--output",
            str(analysis_output),
        ]
    )

    study_plan_output = outdir / "study_plan.md"
    if args.with_study_plan:
        run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent / "plan_study.py"),
                "--input",
                str(analysis_input),
                "--output",
                str(study_plan_output),
                "--title",
                title,
            ]
        )

    print("\nPipeline complete:")
    print(f"- manifest: {outdir / 'manifest.json'}")
    print(f"- analysis: {analysis_output}")
    if args.with_study_plan:
        print(f"- study plan: {study_plan_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
