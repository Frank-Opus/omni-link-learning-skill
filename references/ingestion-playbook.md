# Ingestion Playbook

## Goal

Extract the maximum usable content from one input:
- Bilibili link/name
- Douyin link/name
- Xiaoyuzhou link/name
- Foreign blog/article link/name

## Priority Order

1. Use direct transcript/subtitle if available.
2. Use ASR fallback transcript when subtitles are missing.
3. Use cleaned source text from `r.jina.ai`.
4. Use search digest from `s.jina.ai` for topic-name input.
5. Declare extraction gaps explicitly.

## Commands

### Unified ingestion

```bash
python3 scripts/fetch_source.py --input "<url-or-topic>" --outdir ./omni_learning_output
```

### High-coverage ingestion (video long-form)

```bash
python3 scripts/fetch_source.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh
```

## Platform-Specific Notes

### Bilibili

`fetch_source.py` now does all of the following:
- Normalize watch-later/share URLs to canonical `/video/BV...` when BVID is detectable.
- Read page text through `r.jina.ai/<canonical-url>`.
- Fetch metadata via public APIs (when accessible):
  - title/owner/pubdate/duration/stat
  - tags
  - chapter timeline (`view_points`)
  - subtitle track metadata
- Save metadata file to `platform_meta` (typically `bilibili_meta.json`).

If subtitles are unavailable:
- Enable `--asr-fallback`.
- Requires:
  - `yt-dlp` in PATH
  - faster-whisper runner at `~/.codex/skills/faster-whisper/scripts/transcribe` or `transcribe` in PATH

### Douyin / Xiaoyuzhou

- Try subtitle extraction via `yt-dlp`.
- If transcript still missing, use `--asr-fallback` when local ASR is available.

### Blog/article route

Always available:
- `https://r.jina.ai/<url>` for cleaned article text
- `https://s.jina.ai/<query>` for topic search digest

## Extraction Quality Rubric

- High: coherent transcript exists (subtitle or ASR) and metadata is complete enough for section-level analysis
- Medium: clean article/page text exists, no transcript
- Low: only search digest or partial page content

Always state extraction quality in the final answer and identify specific missing artifacts.
