#!/usr/bin/env python3
"""
Generate a staged learning plan from source text.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path


OBJECTIVES = [
    "Understand the main claim and the author's core intent",
    "Map evidence, examples, and supporting logic",
    "Identify assumptions, caveats, and potential biases",
    "Extract reusable frameworks and practical actions",
    "Synthesize and explain the material in your own words",
]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if parts:
        return parts
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines if lines else [text]


def chunk_paragraphs(paragraphs: list[str], target_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        p_len = len(para)
        if current and current_len + p_len > target_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = p_len
        else:
            current.append(para)
            current_len += p_len

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def make_plan(title: str, text: str, minutes: int, target_chars: int) -> str:
    text = normalize_text(text)
    paragraphs = split_paragraphs(text)
    chunks = chunk_paragraphs(paragraphs, target_chars)

    total_chars = len(text)
    total_sessions = max(1, len(chunks))
    estimated_total_minutes = total_sessions * minutes

    lines = []
    lines.append(f"# Study Plan: {title}")
    lines.append("")
    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"- Source length: ~{total_chars} characters")
    lines.append(f"- Suggested sessions: {total_sessions}")
    lines.append(f"- Session length: ~{minutes} minutes")
    lines.append(f"- Total estimated time: ~{estimated_total_minutes} minutes")
    lines.append("")
    lines.append("## Session Roadmap")
    lines.append("")
    lines.append("| Session | Objective | Work | Output |")
    lines.append("|---|---|---|---|")

    for idx in range(total_sessions):
        objective = OBJECTIVES[idx % len(OBJECTIVES)]
        lines.append(
            f"| S{idx + 1} | {objective} | Read chunk {idx + 1}, write 3 bullets + 1 question | 5-line recap |"
        )

    lines.append("")
    lines.append("## Session Details")
    lines.append("")

    for idx, chunk in enumerate(chunks, start=1):
        preview = chunk[:420].replace("\n", " ").strip()
        if len(chunk) > 420:
            preview += "..."
        objective = OBJECTIVES[(idx - 1) % len(OBJECTIVES)]
        lines.append(f"### Session {idx} ({minutes} min)")
        lines.append("")
        lines.append(f"- Objective: {objective}")
        lines.append("- Before reading: write what you already believe about this topic in 2 lines.")
        lines.append("- During reading: extract 3 claims, 2 evidences, 1 uncertainty.")
        lines.append("- After reading: answer the retrieval questions below without looking back.")
        lines.append("")
        lines.append("Retrieval questions:")
        lines.append("1. What is the strongest claim in this chunk?")
        lines.append("2. Which evidence supports it most directly?")
        lines.append("3. What would fail if the main assumption is wrong?")
        lines.append("")
        lines.append("Chunk preview:")
        lines.append("")
        lines.append(f"> {preview}")
        lines.append("")

    lines.append("## Spaced Review Schedule")
    lines.append("")
    lines.append("- D0: finish all sessions and produce one 10-line synthesis.")
    lines.append("- D1: answer all retrieval questions again from memory.")
    lines.append("- D3: teach the topic to an imaginary beginner in 3 minutes.")
    lines.append("- D7: do one practical transfer task in your own context.")
    lines.append("")
    lines.append("## Mastery Check")
    lines.append("")
    lines.append("- Can you explain the core thesis in 60 seconds?")
    lines.append("- Can you list 3 critical assumptions?")
    lines.append("- Can you apply one idea to a real decision this week?")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate staged study plan from source text.")
    parser.add_argument("--input", required=True, help="Input text/markdown file")
    parser.add_argument("--output", required=True, help="Output markdown path")
    parser.add_argument("--title", default="Untitled Source", help="Plan title")
    parser.add_argument("--minutes-per-session", type=int, default=25, help="Minutes per session")
    parser.add_argument("--target-chars", type=int, default=3500, help="Approx chars per session")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    text = input_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError("Input file is empty.")

    plan = make_plan(
        title=args.title,
        text=text,
        minutes=args.minutes_per_session,
        target_chars=max(1200, args.target_chars),
    )
    output_path.write_text(plan, encoding="utf-8")
    print(f"Wrote study plan: {output_path}")
    print(f"Estimated sessions: {math.ceil(len(text) / max(1200, args.target_chars))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
