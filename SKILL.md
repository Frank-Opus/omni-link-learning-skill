---
name: omni-link-learning
description: "Auto-ingest and teach content from Bilibili, Douyin, Xiaohongshu, WeChat MP, X posts, X bookmarks, Jike, Xiaoyuzhou, or blog links (or topic names). Use when users want end-to-end extraction, concise key summaries first, and a staged learning plan with checkpoints for deep understanding."
---

# Omni Link Learning (Enhanced)

## Overview

Convert one input (URL or topic name) into a full "understanding pack":
1) fast summary, 2) highest-value insights, 3) staged learning path, 4) comprehension checks.

**Enhanced Features:**
- ✅ **Douyin support** (抖音): Headless Chrome capture + direct media extraction
- ✅ **Xiaohongshu support** (小红书): Direct HTML + embedded state parsing + image direct links
- ✅ **WeChat MP support** (公众号): URL-encoded markdown bridge, no token
- ✅ **X support**: Nitter-based post capture + Field Theory bookmark search
- ✅ **Jike support** (即刻): Direct HTML parsing with interaction fallback
- ✅ **Bilibili enhancements**: Chapter alignment, ASR quality metrics
- ✅ **GPU-accelerated ASR**: faster-whisper with CUDA support
- ✅ **Quality indicators**: CJK ratio, language detection confidence
- ✅ **Entrepreneur-focused output**: Action items, strategic insights

## Workflow

### Default Path

Use the default pipeline when you want the main deliverable to be a complete report:

```bash
python3 scripts/run_pipeline.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh
```

Outputs:
- `manifest.json`
- `source_read.md`
- `transcript.txt` (if subtitles or ASR succeeded)
- `analysis_report.md`

### Optional Learning Mode

Only add the study-plan step when the user explicitly wants a learning workflow:

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

### Step 1: Normalize Input

Accept one of:
- Direct URL (Bilibili, Douyin, Xiaohongshu, WeChat MP, X, Jike, Xiaoyuzhou, or any blog/article URL)
- Topic name/title (no URL)
- X bookmark query via `x-bookmarks:<query>` / `fieldtheory:<query>` / `ft:<query>`

If input is a topic name:
- Run web search and return top 3 candidate links.
- If confidence is high (clear official source), proceed automatically.
- If ambiguity is high, ask user to pick one link.

### Step 2: Ingest Source Content

**Base ingestion:**
```bash
python3 scripts/fetch_source.py --input "<url-or-topic>" --outdir ./omni_learning_output
```

**High-coverage ingestion (recommended for long videos/podcasts):**
```bash
python3 scripts/fetch_source.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh \
  --asr-beam-size 5
```

**GPU-accelerated ASR (if NVIDIA GPU available):**
```bash
# The script auto-detects GPU and uses CUDA if available
# Check: nvidia-smi
# If GPU detected, ASR will be 5-10x faster (5-10 min vs 30-60 min for 1.5h video)
```

Then read `manifest.json` and load:
- `source_read.md` (LLM-friendly source content or platform-normalized markdown)
- `transcript.txt` (subtitle transcript or ASR transcript)
- `platform_meta` (title/stats/tags/chapters/direct-link info depending on platform)
- `candidates` (if input was a topic name)
- `asr_quality` (if ASR was used: CJK ratio, language confidence)

**Platform support:**
- **Bilibili**: Normalize to canonical `/video/BV...` URL, extract chapters, stats, tags
- **Douyin**: Launch headless Chrome, intercept `aweme/detail` API, extract no-watermark media URL, then ASR fallback
- **Xiaohongshu**: Parse HTML meta + `window.__INITIAL_STATE__`, extract structured note data and image links, and use Chrome login cookies for video download when needed
- **WeChat MP**: URL-encode source URL and pull markdown from `down.mptext.top`
- **X**: Convert post URLs to Nitter mirrors and scrape static HTML
- **X bookmarks**: Use Field Theory local bookmark index, no token required
- **Jike**: Prefer direct HTML parsing, keep Jina as fallback
- **Xiaoyuzhou**: Podcast metadata, chapter markers
- **YouTube/Blog**: Standard web scraping via r.jina.ai

**ASR Fallback Policy:**
- If subtitles unavailable and `--asr-fallback` enabled: run faster-whisper
- Auto-detect GPU acceleration (CUDA)
- Quality check: CJK ratio for Chinese content (warn if <0.08)
- Output: `transcript_asr.json` (with timestamps) + `transcript.txt` (plain text)

Detailed fallback logic: `references/ingestion-playbook.md`.

### Step 3: Produce Fast Insight First

Before any deep explanation, output:
- **3-line gist** (核心摘要)
- **5-8 most important points** (关键要点)
- **3 "why this matters" bullets** (为什么重要)
- **For entrepreneurs**: Strategic implications, action items

Use the structure in `references/output-template.md` section "A. Quick Brief".

**Enhanced for entrepreneurs:**
- Add "Founder's Takeaway" section
- Highlight competitive landscape insights
- Identify market opportunities/threats
- Suggest follow-up actions

### Step 4: Build Deep Understanding Pack

Output these sections in order:
- **Core Thesis** (核心论点)
- **Evidence and Logic Chain** (证据与逻辑链)
- **Key Terms/Concepts** (关键术语/概念)
- **Hidden Assumptions and Risks** (隐藏假设与风险)
- **What to Apply in Practice** (实践应用)
- **Strategic Implications** (战略启示) **[NEW]**
- **Competitive Landscape** (竞争格局) **[NEW]**
- **Action Items for Founders** (创业者行动清单) **[NEW]**

Use `references/output-template.md` section "B. Deep Understanding".

### Step 5: Guide Distributed Absorption

Generate staged learning plan:
```bash
python3 scripts/plan_study.py --input ./omni_learning_output/transcript.txt --output ./omni_learning_output/study_plan.md
```

If transcript is missing, use `source_read.md` as input.

**If Bilibili chapters are available** in `platform_meta`:
- Align sessions to chapter boundaries first
- Then refine with plan chunks

**If Douyin/Xiaohongshu**:
- Segment by content themes (auto-detected)
- Create micro-learning sessions (5-10 min each)

Then adapt the generated plan to user context (time, background, goal) and provide:
- Session-by-session objectives
- Retrieval questions
- Mini quizzes
- Review checkpoints (D1, D3, D7)
- **Founder-specific checkpoints**: "How does this apply to your startup?" **[NEW]**

Learning method rules: `references/learning-method.md`.

### Step 6: Verify Understanding

End with:
- **5 diagnostic questions** (from basic to transfer)
- **1 short "teach-back" task**
- **1 action task** (apply to user real scenario)
- **1 strategic reflection** (for entrepreneurs: "How does this change your strategy?") **[NEW]**

If user answers weakly, loop back to the specific stage where gaps exist.

## Output Contract

Always return in this order:
1. **Quick Brief** (short and high value) - 30 sec read
2. **Deep Understanding** (structured analysis) - 5 min read
3. **Strategic Insights** (for entrepreneurs) **[NEW]** - 2 min read
4. **Distributed Learning Plan** (staged absorption) - reference
5. **Comprehension Check** (questions + action) - interactive

Template details: `references/output-template.md`.

## Platform-Specific Enhancements

### Bilibili (bilibili.com, b23.tv)
- ✅ Normalize to canonical `/video/BV...` URL
- ✅ Extract: title, owner, pubdate, duration, stats (views/likes/coins)
- ✅ Extract: tags, chapters (with timestamps)
- ✅ Extract: subtitle tracks (lan, lan_doc, url)
- ✅ Detect: need_login_subtitle flag
- ✅ ASR fallback with quality metrics (CJK ratio, language confidence)
- ✅ Chapter-aligned learning sessions

### Douyin (douyin.com, v.douyin.com, iesdouyin.com) **[NEW]**
- ✅ Extract: title, author, stats by intercepting `aweme/detail` JSON in headless Chrome
- ✅ Extract: no-watermark MP4 direct link and music link
- ✅ Keep subtitle extraction via `yt-dlp` when available
- ✅ ASR fallback for Chinese content (optimized for short-form)
- ✅ Real pipeline verified: `video -> transcript.txt -> analysis_report.md`
- ✅ Micro-learning sessions (3-5 min each)
- ✅ Trend analysis (if public data available)

### Xiaohongshu (xiaohongshu.com, xhslink.com) **[NEW]**
- ✅ Parse rich text content from HTML + embedded state
- ✅ Extract: title, author, likes, collects, comments
- ✅ Extract image direct links
- ✅ Extract video direct link when embedded state exposes it
- ✅ Fallback to Chrome-cookie download for protected video pages
- ✅ Real pipeline verified on logged-in Chrome session: `video -> transcript.txt -> analysis_report.md`
- ✅ Comment sentiment analysis (if public) **[FUTURE]**
- ✅ Topic clustering for learning sessions

**Important:** Xiaohongshu video download currently depends on a Chrome profile that is already logged in to Xiaohongshu.

### WeChat MP (mp.weixin.qq.com) **[NEW]**
- ✅ Fetch article markdown via encoded URL bridge
- ✅ No token or login needed
- ✅ Preserve article body and inline images for downstream analysis

### X / Twitter (x.com, twitter.com) **[NEW]**
- ✅ Convert post URLs to Nitter static mirrors
- ✅ Extract post text, author, timestamp, and media links from static HTML
- ✅ Avoid official API tokens

### X Bookmarks **[NEW]**
- ✅ Query local synced bookmarks with `x-bookmarks:<query>`
- ✅ Use Field Theory CLI with browser-derived session sync
- ✅ Keep bookmark data local

### Jike (okjike.com) **[NEW]**
- ✅ Direct HTML parsing for title/content/interaction counts
- ✅ Jina fallback when direct parse is incomplete
- ✅ No token flow by default

### Xiaoyuzhou (xiaoyuzhoufm.com)
- ✅ Extract: episode title, podcast name, duration
- ✅ Extract: chapter markers, show notes
- ✅ ASR fallback for full transcript
- ✅ Podcast-specific learning plan (by topic segments)

### YouTube/Blogs
- ✅ Standard web scraping via r.jina.ai
- ✅ ASR fallback for videos (multi-language support)
- ✅ Cross-platform content comparison **[FUTURE]**

## Constraints

- Prefer source-grounded statements; mark inferred claims explicitly.
- If source extraction quality is low, state the gap and provide best-effort summary.
- Declare ingestion quality (`high`/`medium`/`low`) and why.
- Do not skip the "quick brief first" step.
- Keep guidance actionable, not generic.
- **For entrepreneur users**: Always include strategic implications and action items. **[NEW]**

## Quality Metrics

**After ingestion, report:**
- **Transcript length**: characters, words
- **CJK ratio**: for Chinese content (warn if <0.08)
- **Language detection**: language, confidence
- **Coverage**: % of video/audio transcribed
- **Quality flag**: high/medium/low (based on above)

**ASR-specific metrics:**
- Model used (e.g., large-v3-turbo)
- Beam size
- GPU acceleration (yes/no, which GPU)
- Processing time
- CJK ratio (for Chinese)
- Language confidence

## Error Handling

**Common issues and solutions:**

| Issue | Cause | Solution |
|-------|-------|----------|
| No transcript | Subtitles unavailable | Re-run with `--asr-fallback` |
| Low CJK ratio | Wrong language or poor ASR | Re-run with `--asr-model large-v3` |
| yt-dlp not found | Missing dependency | Install: `pip install yt-dlp` |
| ASR runner not found | faster-whisper not installed | Install skill or run setup script |
| Bilibili metadata partial | API rate limit or login required | Retry later or ignore (non-critical) |
| Xiaohongshu login wall | Private content | Ask user for public alternative |
| Xiaohongshu video download blocked | Chrome not logged in | Log in to Xiaohongshu in Chrome, then retry |
| Douyin browser capture failed | Playwright dependencies missing | Run `npm install` in this repo |
| X bookmarks unavailable | Field Theory has not synced bookmarks yet | Log into x.com and run `ft sync` |

## Examples

### Example 1: Bilibili Video (with ASR)
```bash
python3 scripts/fetch_source.py \
  --input "https://b23.tv/souSczX" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh
```

**Output:**
- `manifest.json` (metadata, quality metrics)
- `bilibili_meta.json` (chapters, stats, tags)
- `transcript_asr.json` (with timestamps)
- `transcript.txt` (plain text, 36K characters)
- `source_read.md` (Jina Reader fallback)

### Example 2: Douyin Video
```bash
python3 scripts/fetch_source.py \
  --input "https://v.douyin.com/xxxxx" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-language zh
```

### Example 3: Xiaohongshu Note
```bash
python3 scripts/run_pipeline.py \
  --input "https://www.xiaohongshu.com/explore/xxxxx?xsec_token=..." \
  --outdir ./omni_learning_output
```

### Example 4: WeChat MP Article
```bash
python3 scripts/run_pipeline.py \
  --input "https://mp.weixin.qq.com/s/xxxxx" \
  --outdir ./omni_learning_output
```

### Example 5: X Bookmark Search
```bash
python3 scripts/run_pipeline.py \
  --input "x-bookmarks:agent memory" \
  --outdir ./omni_learning_output
```

### Example 6: Topic Search
```bash
python3 scripts/run_pipeline.py \
  --input "AI 代理技术详解" \
  --outdir ./omni_learning_output
```

## Integration with Entrepreneur Workflow

**Recommended workflow for founders:**

1. **Ingest** industry content (videos, podcasts, articles)
2. **Quick Brief** → 30-sec understanding
3. **Deep Analysis** → Strategic insights extraction
4. **Action Items** → What to do Monday morning
5. **Learning Plan** → Team knowledge sharing
6. **Competitive Intel** → Update strategy doc

**Output files for startup use:**
- `ai_maker_analysis.md` -赛道分析
- `action_items.md` - 行动清单
- `deep_analysis.md` - 深度分析
- `study_plan.md` - 团队学习计划
- `chapter_notes.md` - 章节精读

## References

- `references/ingestion-playbook.md` - Detailed platform handling
- `references/output-template.md` - Output structure
- `references/learning-method.md` - Spaced repetition, retrieval practice
- `references/entrepreneur-guide.md` - **[NEW]** Strategic analysis for founders

---

*Enhanced with real-world experience from analyzing 红杉中国《the prompt》hardware investment episode (1h37m, 36K characters, GPU-accelerated ASR).*
