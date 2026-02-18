---
name: omni-link-learning
description: "Auto-ingest and teach content from Bilibili, Douyin, Xiaoyuzhou, or foreign blog links (or topic names). Use when users want end-to-end extraction, concise key summaries first, and a staged learning plan with checkpoints for deep understanding. Includes Bilibili chapter metadata extraction and optional ASR fallback for full transcript when subtitles are missing."
---

# Omni Link Learning

## Overview

Convert one input (URL or topic name) into a full "understanding pack":
1) fast summary, 2) highest-value insights, 3) staged learning path, 4) comprehension checks.

## Workflow

### Step 1: Normalize Input

Accept one of:
- Direct URL (Bilibili, Douyin, Xiaoyuzhou, or any blog/article URL)
- Topic name/title (no URL)

If input is a topic name:
- Run web search and return top 3 candidate links.
- If confidence is high (clear official source), proceed automatically.
- If ambiguity is high, ask user to pick one link.

### Step 2: Ingest Source Content

Base ingestion:
```bash
python3 scripts/fetch_source.py --input "<url-or-topic>" --outdir ./omni_learning_output
```

High-coverage ingestion (recommended for long videos):
```bash
python3 scripts/fetch_source.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh
```

Then read `manifest.json` and load:
- `source_read.md` (LLM-friendly source content via Jina Reader/Search)
- `transcript.txt` (subtitle transcript or ASR transcript)
- `platform_meta` (for Bilibili: title/stats/tags/chapters/subtitle-track info)
- `candidates` (if input was a topic name)

Platform policy:
- Bilibili: normalize to canonical `/video/BV...` URL when possible.
- Bilibili/Douyin/Xiaoyuzhou: attempt subtitle extraction via `yt-dlp` when available.
- If subtitles are unavailable and `--asr-fallback` is enabled: run local faster-whisper fallback.
- Any web/blog URL: always fetch cleaned content via `https://r.jina.ai/<url>`.
- Topic name: fetch search digest via `https://s.jina.ai/<query>`.

Detailed fallback logic: `references/ingestion-playbook.md`.

### Step 3: Produce Fast Insight First

Before any deep explanation, output:
- 3-line gist
- 5-8 most important points
- 3 "why this matters" bullets

Use the structure in `references/output-template.md` section "A. Quick Brief".

### Step 4: Build Deep Understanding Pack

Output these sections in order:
- Core Thesis
- Evidence and Logic Chain
- Key Terms/Concepts
- Hidden Assumptions and Risks
- What to Apply in Practice

Use `references/output-template.md` section "B. Deep Understanding".

### Step 5: Guide Distributed Absorption

Generate staged learning plan:
```bash
python3 scripts/plan_study.py --input ./omni_learning_output/transcript.txt --output ./omni_learning_output/study_plan.md
```

If transcript is missing, use `source_read.md` as input.

If Bilibili chapters are available in `platform_meta`, align sessions to chapter boundaries first, then refine with plan chunks.

Then adapt the generated plan to user context (time, background, goal) and provide:
- Session-by-session objectives
- Retrieval questions
- Mini quizzes
- Review checkpoints (D1, D3, D7)

Learning method rules: `references/learning-method.md`.

### Step 6: Verify Understanding

End with:
- 5 diagnostic questions (from basic to transfer)
- 1 short "teach-back" task
- 1 action task (apply to user real scenario)

If user answers weakly, loop back to the specific stage where gaps exist.

## Output Contract

Always return in this order:
1. Quick Brief (short and high value)
2. Deep Understanding (structured analysis)
3. Distributed Learning Plan (staged absorption)
4. Comprehension Check (questions + action)

Template details: `references/output-template.md`.

## Constraints

- Prefer source-grounded statements; mark inferred claims explicitly.
- If source extraction quality is low, state the gap and provide best-effort summary.
- Declare ingestion quality (`high`/`medium`/`low`) and why.
- Do not skip the "quick brief first" step.
- Keep guidance actionable, not generic.
