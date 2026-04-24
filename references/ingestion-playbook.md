# Ingestion Playbook

## Goal

Extract the maximum usable content from one input:
- Bilibili link/name
- Douyin link/name
- Xiaohongshu link/name
- WeChat MP article
- X post or X bookmark query
- Jike post
- Xiaoyuzhou link/name
- Foreign blog/article link/name

## Priority Order

1. Use direct transcript/subtitle if available.
2. Use platform-native no-token extraction when available.
3. Use ASR fallback transcript when subtitles are missing.
4. Use cleaned source text from `r.jina.ai`.
5. Use search digest from `s.jina.ai` for topic-name input.
6. Declare extraction gaps explicitly.

## Commands

### Unified ingestion

```bash
python3 scripts/fetch_source.py --input "<url-or-topic>" --outdir ./omni_learning_output
```

### Default report pipeline

```bash
python3 scripts/run_pipeline.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh
```

This produces:
- `manifest.json`
- `source_read.md`
- `transcript.txt` when available
- `analysis_report.md`

### Optional learning plan

Only generate the learning plan when the user explicitly wants it:

```bash
python3 scripts/run_pipeline.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh \
  --with-study-plan
```

Additional output:
- `study_plan.md`

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

### Douyin

- Normalize short links by following redirects first.
- Launch headless Chrome with Playwright.
- Intercept Douyin `aweme/detail`-style API responses from the page session.
- Extract `play_addr.url_list[0]` or equivalent direct media URL.
- Use `yt-dlp` with `Referer: https://www.douyin.com/` to download video/audio for ASR.
- If direct URL capture fails, fall back to page URL plus `--cookies-from-browser chrome`.

### Xiaohongshu

- Fetch raw HTML with a browser-like user agent.
- Read meta tags first for title/description fallback.
- Parse `window.__INITIAL_STATE__` / SSR state for structured note payload.
- Extract image direct links and embedded video links when present.
- Keep `xsec_token` and related query params when normalizing URL.
- Use `--cookies-from-browser chrome` for video download on protected pages.
- If embedded state does not expose the video URL, try browser-network capture.
- If the note is video and transcript is needed, use `--asr-fallback`.
- Requires: Chrome already logged in to Xiaohongshu.

### WeChat MP

- Use the encoded URL bridge:
  - URL encode the article link
  - Call `https://down.mptext.top/api/public/v1/download?url=<encoded>&format=markdown`
- Save returned markdown to `source_read.md`.

### X Posts

- Convert `x.com` / `twitter.com` URLs to Nitter mirror URLs.
- Scrape static HTML for author, text, timestamp, and media links.
- Keep Nitter as the primary route because it avoids official API tokens.

### X Bookmarks

- Use `x-bookmarks:<query>` or `fieldtheory:<query>` as input.
- Ensure bookmarks are synced locally first:
  - login to x.com in a local browser
  - run `ft sync`
- Use `ft search <query>` for retrieval.

### Jike

- Prefer direct HTML parsing for content and interactions.
- Fall back to `r.jina.ai` when direct HTML lacks enough text.

### Xiaoyuzhou

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
