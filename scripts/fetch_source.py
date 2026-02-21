#!/usr/bin/env python3
"""
Fetch and normalize source content for omni-link-learning skill.

Supports:
- URL input: fetches LLM-friendly content via r.jina.ai
- Topic input: fetches search digest via s.jina.ai
- Video/audio platforms (Bilibili/Douyin/Xiaoyuzhou): tries yt-dlp subtitles when available

Enhancements:
- Bilibili canonical URL normalization (watchlater -> /video/BV...)
- Bilibili metadata enrichment (title/stats/tags/chapters/subtitle tracks)
- Optional ASR fallback via faster-whisper wrapper
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


PLATFORM_DOMAINS = {
    "bilibili": ("bilibili.com", "b23.tv"),
    "douyin": ("douyin.com", "iesdouyin.com", "v.douyin.com", "www.douyin.com"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com", "www.xiaohongshu.com"),
    "xiaoyuzhou": ("xiaoyuzhoufm.com",),
}

UA = "Mozilla/5.0 omni-link-learning/1.1"


def is_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def detect_platform(value: str) -> str:
    host = urlparse(value).netloc.lower()
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(d in host for d in domains):
            return platform
    return "web"


def http_get_text(url: str, timeout: int, headers: dict[str, str] | None = None, allow_redirects: bool = True) -> str:
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    
    # Handle redirects manually for better control
    if allow_redirects:
        redirect_count = 0
        max_redirects = 5
        current_url = url
        
        while redirect_count < max_redirects:
            try:
                req = Request(current_url, headers=req_headers)
                with urlopen(req, timeout=timeout) as resp:
                    # Check if this is a redirect
                    if resp.url != current_url and resp.url != url:
                        redirect_count += 1
                        current_url = resp.url
                        continue
                    
                    charset = resp.headers.get_content_charset() or "utf-8"
                    return resp.read().decode(charset, errors="replace")
            except Exception as e:
                # If redirect fails, try the original URL without redirects
                if redirect_count > 0:
                    req = Request(url, headers=req_headers)
                    with urlopen(req, timeout=timeout) as resp:
                        charset = resp.headers.get_content_charset() or "utf-8"
                        return resp.read().decode(charset, errors="replace")
                raise
        raise TimeoutError(f"Too many redirects for {url}")
    else:
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")


def http_get_json(url: str, timeout: int, headers: dict[str, str] | None = None) -> dict:
    raw = http_get_text(url, timeout, headers=headers)
    return json.loads(raw)


def fetch_duckduckgo_html(query: str, timeout: int) -> str:
    ddg_url = f"https://duckduckgo.com/html/?q={quote(query)}"
    return http_get_text(ddg_url, timeout), ddg_url


def clean_subtitle_text(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.upper().startswith("WEBVTT"):
            continue
        if s.isdigit():
            continue
        if "-->" in s:
            continue
        if re.match(r"^\d{1,2}:\d{2}:\d{2}", s):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"\{\\an\d+\}", "", s)
        if s:
            lines.append(s)

    dedup = []
    for line in lines:
        if not dedup or dedup[-1] != line:
            dedup.append(line)
    return "\n".join(dedup).strip()


def extract_candidate_urls(text: str, limit: int = 5) -> list[str]:
    uniq: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return
        host = parsed.netloc.lower()
        if not host:
            return
        if "duckduckgo.com" in host:
            return
        if host in {"www.w3.org", "w3.org"}:
            return
        if url not in seen:
            seen.add(url)
            uniq.append(url)

    for encoded in re.findall(r"uddg=([^&\"'>]+)", text):
        add(unquote(encoded))
        if len(uniq) >= limit:
            return uniq

    for url in re.findall(r"https?://[^\s)>\]\"']+", text):
        add(url)
        if len(uniq) >= limit:
            break

    return uniq


def collect_subtitles(outdir: Path) -> list[Path]:
    candidates = []
    for pattern in ("*.srt", "*.vtt"):
        candidates.extend(outdir.rglob(pattern))
    return sorted(set(candidates))


def try_extract_subtitles(source_url: str, outdir: Path) -> dict:
    result: dict[str, object] = {
        "yt_dlp_available": False,
        "subtitle_files": [],
        "transcript_path": None,
        "note": "",
    }
    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        result["note"] = "yt-dlp not found; skipped subtitle extraction."
        return result

    result["yt_dlp_available"] = True
    cmd = [
        yt_dlp,
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "all",
        "--convert-subs",
        "srt",
        "-o",
        str(outdir / "media.%(ext)s"),
        source_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    subtitle_files = collect_subtitles(outdir)
    result["subtitle_files"] = [str(p) for p in subtitle_files]

    if not subtitle_files:
        result["note"] = (
            "yt-dlp ran but no subtitles found. "
            "Consider ASR fallback with --asr-fallback."
        )
        return result

    blocks = []
    for path in subtitle_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            cleaned = clean_subtitle_text(text)
            if cleaned:
                blocks.append(f"## {path.name}\n\n{cleaned}")
        except Exception as exc:  # noqa: BLE001
            blocks.append(f"## {path.name}\n\n[Failed to parse subtitle: {exc}]")

    transcript = "\n\n".join(blocks).strip()
    if transcript:
        transcript_path = outdir / "transcript.txt"
        transcript_path.write_text(transcript, encoding="utf-8")
        result["transcript_path"] = str(transcript_path)
    else:
        result["note"] = "Subtitle files were present but contained no usable text."

    if proc.returncode != 0 and not result["note"]:
        result["note"] = "yt-dlp returned non-zero exit code but some subtitle output was captured."
    return result


def extract_bilibili_bvid(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    bvid = query.get("bvid", [None])[0]
    if bvid:
        return bvid

    m = re.search(r"/video/(BV[0-9A-Za-z]{10})", parsed.path)
    if m:
        return m.group(1)

    m = re.search(r"(BV[0-9A-Za-z]{10})", url)
    if m:
        return m.group(1)
    return None


def extract_douyin_video_id(url: str) -> str | None:
    """Extract Douyin video ID from various URL formats."""
    parsed = urlparse(url)
    
    # Short URL: https://v.douyin.com/xxxxx/
    m = re.search(r"v\.douyin\.com/([^/?]+)", url)
    if m:
        return m.group(1)
    
    # Full URL: https://www.douyin.com/video/xxxxx
    m = re.search(r"douyin\.com/video/([^/?]+)", url)
    if m:
        return m.group(1)
    
    # Mobile URL: https://m.douyin.com/share/video/xxxxx
    m = re.search(r"share/video/([^/?]+)", url)
    if m:
        return m.group(1)
    
    return None


def extract_xiaohongshu_note_id(url: str) -> str | None:
    """Extract Xiaohongshu note ID from URL."""
    parsed = urlparse(url)
    
    # Standard: https://www.xiaohongshu.com/explore/xxxxx
    m = re.search(r"explore/([a-zA-Z0-9]+)", parsed.path)
    if m:
        return m.group(1)
    
    # Short: https://xhslink.com/xxxxx
    m = re.search(r"xhslink\.com/([^/?]+)", url)
    if m:
        return m.group(1)
    
    # Mobile: https://www.xiaohongshu.com/discovery/item/xxxxx
    m = re.search(r"discovery/item/([a-zA-Z0-9]+)", parsed.path)
    if m:
        return m.group(1)
    
    return None


def normalize_source_url(source: str, platform: str) -> str:
    """Normalize platform URLs to canonical form."""
    if platform == "bilibili":
        bvid = extract_bilibili_bvid(source)
        if bvid:
            return f"https://www.bilibili.com/video/{bvid}"
        return source
    
    elif platform == "douyin":
        video_id = extract_douyin_video_id(source)
        if video_id:
            # Prefer mobile share URL for better compatibility
            return f"https://m.douyin.com/share/video/{video_id}"
        return source
    
    elif platform == "xiaohongshu":
        note_id = extract_xiaohongshu_note_id(source)
        if note_id:
            return f"https://www.xiaohongshu.com/explore/{note_id}"
        return source
    
    return source


def sec_to_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def fetch_douyin_metadata(source_url: str, timeout: int) -> dict:
    """Fetch Douyin video metadata via multiple strategies."""
    meta: dict[str, object] = {
        "canonical_url": source_url,
        "video_id": extract_douyin_video_id(source_url),
        "errors": [],
        "strategies_tried": [],
    }
    
    video_id = meta["video_id"]
    
    # Strategy 1: Try Jina Reader first
    try:
        meta["strategies_tried"].append("jina_reader")
        read_url = f"https://r.jina.ai/{source_url}"
        content = http_get_text(read_url, timeout)
        
        if content and len(content) > 100:
            # Extract title from common patterns
            title_match = re.search(r'"desc":"([^"]+)"', content)
            if title_match:
                meta["title"] = title_match.group(1)
            
            author_match = re.search(r'"nickname":"([^"]+)"', content)
            if author_match:
                meta["author"] = author_match.group(1)
            
            like_match = re.search(r'"digg_count":(\d+)', content)
            if like_match:
                meta["like_count"] = int(like_match.group(1))
            
            meta["raw_content_length"] = len(content)
            meta["strategy_success"] = "jina_reader"
            return meta
    except Exception as exc:  # noqa: BLE001
        meta["errors"].append(f"Jina Reader failed: {exc}")
    
    # Strategy 2: Try Douyin mobile web API (if we have video ID)
    if video_id:
        try:
            meta["strategies_tried"].append("douyin_mobile_api")
            # Try to fetch via Douyin's mobile web interface
            mobile_url = f"https://m.douyin.com/share/video/{video_id}"
            mobile_content = http_get_text(mobile_url, timeout, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            
            if mobile_content:
                # Look for embedded JSON data
                json_match = re.search(r'window\._ROUTER_DATA\s*=\s*({.+?});', mobile_content)
                if json_match:
                    import json as json_lib
                    try:
                        router_data = json_lib.loads(json_match.group(1))
                        # Extract video info from router data structure
                        # This is platform-specific and may change
                        meta["mobile_api_success"] = True
                        meta["strategy_success"] = "douyin_mobile_api"
                        return meta
                    except Exception:
                        pass
                
                # Fallback: extract from HTML meta tags
                title_match = re.search(r'<title>([^<]+)</title>', mobile_content)
                if title_match:
                    meta["title"] = title_match.group(1).replace("- 抖音", "").strip()
                
                meta["raw_content_length"] = len(mobile_content)
                meta["strategy_success"] = "douyin_mobile_api"
                return meta
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"Mobile API failed: {exc}")
    
    # Strategy 3: Use alternative reader services
    try:
        meta["strategies_tried"].append("alternative_readers")
        
        # Try r.jina.ai with different parameters
        reader_urls = [
            f"https://r.jina.ai/{source_url}",
            f"https://r.jina.ai/http/{source_url}",
        ]
        
        for reader_url in reader_urls:
            try:
                content = http_get_text(reader_url, timeout + 10)  # Longer timeout
                if content and len(content) > 50:
                    meta["raw_content_length"] = len(content)
                    meta["reader_url_used"] = reader_url
                    meta["strategy_success"] = "alternative_readers"
                    return meta
            except Exception:
                continue
    except Exception as exc:  # noqa: BLE001
        meta["errors"].append(f"Alternative readers failed: {exc}")
    
    # All strategies failed - provide graceful degradation
    meta["errors"].append("All metadata extraction strategies failed. Will rely on ASR fallback.")
    meta["degradation_mode"] = True
    return meta


def fetch_xiaohongshu_metadata(source_url: str, timeout: int) -> dict:
    """Fetch Xiaohongshu note metadata via Jina Reader."""
    meta: dict[str, object] = {
        "canonical_url": source_url,
        "note_id": extract_xiaohongshu_note_id(source_url),
        "errors": [],
    }
    
    try:
        read_url = f"https://r.jina.ai/{source_url}"
        content = http_get_text(read_url, timeout)
        
        # Extract title (usually at the beginning)
        lines = content.split('\n')
        if len(lines) > 0 and lines[0].strip():
            meta["title"] = lines[0].strip()
        
        # Extract author
        author_match = re.search(r'作者：([^\n]+)', content)
        if author_match:
            meta["author"] = author_match.group(1).strip()
        
        # Extract stats (likes, collects)
        like_match = re.search(r'(\d+)\s*点赞', content)
        if like_match:
            meta["like_count"] = int(like_match.group(1))
        
        collect_match = re.search(r'(\d+)\s*收藏', content)
        if collect_match:
            meta["collect_count"] = int(collect_match.group(1))
        
        comment_match = re.search(r'(\d+)\s*评论', content)
        if comment_match:
            meta["comment_count"] = int(comment_match.group(1))
        
        # Extract content body (after title and metadata)
        content_start = 0
        for i, line in enumerate(lines[1:10], 1):
            if '发表于' in line or 'IP' in line:
                content_start = i + 1
                break
        
        if content_start < len(lines):
            meta["content_preview"] = '\n'.join(lines[content_start:content_start+5]).strip()
        
        meta["raw_content_length"] = len(content)
        
    except Exception as exc:  # noqa: BLE001
        meta["errors"].append(f"Metadata fetch failed: {exc}")
    
    return meta


def fetch_bilibili_metadata(source_url: str, timeout: int) -> dict:
    bvid = extract_bilibili_bvid(source_url)
    meta: dict[str, object] = {
        "canonical_url": source_url,
        "bvid": bvid,
        "errors": [],
    }
    if not bvid:
        meta["errors"].append("No BVID detected from URL.")
        return meta

    try:
        view = http_get_json(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except Exception as exc:  # noqa: BLE001
        meta["errors"].append(f"view api failed: {exc}")
        return meta

    if view.get("code") != 0:
        meta["errors"].append(f"view api returned code={view.get('code')}")
        return meta

    data = view.get("data") or {}
    aid = data.get("aid")
    cid = data.get("cid")

    meta["aid"] = aid
    meta["cid"] = cid
    meta["title"] = data.get("title")
    meta["owner"] = (data.get("owner") or {}).get("name")
    meta["pubdate"] = data.get("pubdate")
    meta["duration_sec"] = data.get("duration")
    meta["desc"] = data.get("desc")
    meta["stat"] = data.get("stat") or {}

    tags: list[str] = []
    if aid:
        try:
            tag_resp = http_get_json(
                f"https://api.bilibili.com/x/tag/archive/tags?aid={aid}",
                timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if tag_resp.get("code") == 0:
                tags = [x.get("tag_name") for x in (tag_resp.get("data") or []) if x.get("tag_name")]
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"tag api failed: {exc}")
    meta["tags"] = tags

    chapters = []
    subtitle_tracks = []
    need_login_subtitle = None
    if aid and cid:
        try:
            player = http_get_json(
                f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}",
                timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if player.get("code") == 0:
                pdat = player.get("data") or {}
                view_points = pdat.get("view_points") or []
                for item in view_points:
                    start = int(item.get("from") or 0)
                    end = int(item.get("to") or 0)
                    chapters.append(
                        {
                            "title": item.get("content"),
                            "start_sec": start,
                            "end_sec": end,
                            "start_hms": sec_to_hms(start),
                            "end_hms": sec_to_hms(end),
                        }
                    )

                subtitle = pdat.get("subtitle") or {}
                need_login_subtitle = pdat.get("need_login_subtitle")
                for sub in subtitle.get("subtitles") or []:
                    subtitle_tracks.append(
                        {
                            "id": sub.get("id"),
                            "lan": sub.get("lan"),
                            "lan_doc": sub.get("lan_doc"),
                            "subtitle_url": sub.get("subtitle_url"),
                        }
                    )
            else:
                meta["errors"].append(f"player api returned code={player.get('code')}")
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"player api failed: {exc}")

    meta["chapters"] = chapters
    meta["subtitle_tracks"] = subtitle_tracks
    meta["need_login_subtitle"] = need_login_subtitle
    return meta


def find_fw_transcribe_runner() -> str | None:
    local_runner = Path.home() / ".codex/skills/faster-whisper/scripts/transcribe"
    if local_runner.exists() and os.access(local_runner, os.X_OK):
        return str(local_runner)

    path_runner = shutil.which("transcribe")
    if path_runner:
        return path_runner
    return None


def try_mcp_download(source_url: str, outdir: Path) -> dict:
    """Try to download Douyin/Xiaohongshu video using MCP (Model Context Protocol)."""
    result: dict[str, object] = {
        "mcp_used": False,
        "download_url": None,
        "audio_path": None,
        "video_info": None,
        "note": "",
    }
    
    platform = detect_platform(source_url)
    if platform not in {"douyin", "xiaohongshu"}:
        result["note"] = "MCP download only supports Douyin and Xiaohongshu."
        return result
    
    # Try to import MCP module
    try:
        from douyin_mcp_server.server import parse_douyin_link, parse_xhs_link
        result["mcp_used"] = True
    except ImportError:
        result["note"] = "MCP module not found. Install with: pip install douyin-mcp-server"
        return result
    
    # Load config for API key
    config_path = Path.home() / ".openclaw" / "skills" / "omni-link-learning" / "config.json"
    api_key = None
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                api_key = config.get("api_key")
        except Exception:
            pass
    
    # Set API key as environment variable
    if api_key:
        os.environ["DASHSCOPE_API_KEY"] = api_key
    
    try:
        # Parse video info and get download link
        if platform == "douyin":
            result_str = parse_douyin_link(source_url)
        else:  # xiaohongshu
            result_str = parse_xhs_link(source_url)
        
        mcp_result = json.loads(result_str) if isinstance(result_str, str) else result_str
        result["video_info"] = mcp_result
        
        if isinstance(mcp_result, dict) and mcp_result.get("status") == "success":
            # Get download URL - check multiple field names
            download_url = (
                mcp_result.get("download_url") or 
                mcp_result.get("video_url") or 
                mcp_result.get("url") or 
                mcp_result.get("play_url")
            )
            
            if download_url:
                result["download_url"] = download_url
                result["note"] = "MCP successfully obtained download link"
                
                # Download audio using yt-dlp
                yt_dlp = shutil.which("yt-dlp")
                if yt_dlp:
                    audio_pattern = outdir / "mcp_audio.%(ext)s"
                    dl_cmd = [
                        yt_dlp,
                        "-x",
                        "--audio-format",
                        "mp3",
                        "--audio-quality",
                        "0",
                        "--no-playlist",
                        "-o",
                        str(audio_pattern),
                        download_url,
                    ]
                    
                    dl = subprocess.run(dl_cmd, capture_output=True, text=True, check=False)
                    if dl.returncode == 0:
                        audio_files = sorted(outdir.glob("mcp_audio.*"), key=lambda p: p.stat().st_mtime, reverse=True)
                        if audio_files:
                            result["audio_path"] = str(audio_files[0])
                            result["note"] = "MCP download + audio extraction successful"
                        else:
                            result["note"] = "Download completed but audio file not found"
                    else:
                        result["note"] = f"Audio extraction failed: {dl.stderr[-300:]}"
            else:
                result["note"] = "MCP returned success but no download URL found"
        else:
            error_msg = mcp_result.get("error", "Unknown error") if isinstance(mcp_result, dict) else "Unknown error"
            result["note"] = f"MCP failed: {error_msg}"
    
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"MCP exception: {exc}"
        import traceback
        result["traceback"] = traceback.format_exc()
    
    return result


def try_asr_fallback(
    source_url: str,
    outdir: Path,
    model: str,
    language: str,
    beam_size: int,
) -> dict:
    result: dict[str, object] = {
        "asr_used": False,
        "audio_path": None,
        "asr_json": None,
        "transcript_path": None,
        "asr_runner": None,
        "model": model,
        "note": "",
        "quality": {},
        "download_attempts": [],
    }

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        result["note"] = "ASR fallback skipped: yt-dlp not found."
        return result

    runner = find_fw_transcribe_runner()
    if not runner:
        result["note"] = (
            "ASR fallback skipped: faster-whisper runner not found. "
            "Expected ~/.codex/skills/faster-whisper/scripts/transcribe or transcribe in PATH."
        )
        return result

    result["asr_runner"] = runner

    # For Douyin/Xiaohongshu, try MCP download first
    platform = detect_platform(source_url)
    if platform in {"douyin", "xiaohongshu"}:
        mcp_result = try_mcp_download(source_url, outdir)
        if mcp_result.get("audio_path"):
            result["audio_path"] = mcp_result["audio_path"]
            result["video_info"] = mcp_result.get("video_info")
            result["download_attempts"].append(f"MCP download successful: {mcp_result['audio_path']}")
            result["asr_used"] = True  # Mark as we have audio, proceed to ASR
            
            # Continue to ASR transcription with the downloaded audio
            audio_path = mcp_result["audio_path"]
        else:
            result["download_attempts"].append(f"MCP download failed: {mcp_result.get('note', 'Unknown')}")
            # Fall back to direct yt-dlp attempt
            audio_path = None
    else:
        # Non-Douyin/Xiaohongshu platforms, use original logic
        audio_path = None

    # If MCP didn't provide audio, try direct yt-dlp
    if not audio_path:
        # Try multiple URL formats for Douyin (anti-scraping workaround)
        urls_to_try = [source_url]
        
        if platform == "douyin":
            video_id = extract_douyin_video_id(source_url)
            if video_id:
                # Try different Douyin URL formats
                urls_to_try = [
                    source_url,  # Original URL
                    f"https://www.douyin.com/video/{video_id}",  # Desktop format
                    f"https://m.douyin.com/share/video/{video_id}",  # Mobile format
                    f"https://iesdouyin.com/share/video/{video_id}",  # Alternative domain
                ]
                result["download_attempts"] = urls_to_try

        audio_pattern = outdir / "asr_audio.%(ext)s"
        dl_success = False
        last_error = None
        
        for attempt_url in urls_to_try:
            result["download_attempts"].append(f"Trying: {attempt_url}")
            
            dl_cmd = [
                yt_dlp,
                "-x",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "0",
                "--no-playlist",
                "--no-warnings",
                "-o",
                str(audio_pattern),
                attempt_url,
            ]
            
            # Add cookies for Douyin if available
            if platform == "douyin":
                # Try to use browser cookies if available
                dl_cmd.extend(["--cookies-from-browser", "chrome"])
            
            dl = subprocess.run(dl_cmd, capture_output=True, text=True, check=False)
            
            if dl.returncode == 0:
                dl_success = True
                result["download_attempts"].append(f"Success with: {attempt_url}")
                break
            else:
                last_error = dl.stderr[-500:] if dl.stderr else "Unknown error"
                result["download_attempts"].append(f"Failed: {attempt_url} - {last_error[:200]}")
        
        if not dl_success:
            result["note"] = f"ASR fallback failed to download audio after {len(urls_to_try)} attempts: {last_error}"
            return result
        
        audio_path = str(audio_pattern)
        # Find the actual file
        audio_files = sorted(outdir.glob("asr_audio.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if audio_files:
            audio_path = str(audio_files[0])
        else:
            result["note"] = "Download completed but audio file not found"
            return result

    # Proceed to ASR transcription
    asr_json_path = outdir / "transcript_asr.json"
    asr_cmd = [
        runner,
        audio_path,
        "--model",
        model,
        "--beam-size",
        str(beam_size),
        "--vad",
        "-j",
        "-o",
        str(asr_json_path),
    ]
    if language:
        asr_cmd.extend(["--language", language])

    asr = subprocess.run(asr_cmd, capture_output=True, text=True, check=False)
    if asr.returncode != 0:
        result["note"] = f"ASR fallback failed during transcription: {asr.stderr[-600:]}"
        return result

    if not asr_json_path.exists():
        result["note"] = "ASR fallback failed: transcript_asr.json not created."
        return result

    result["asr_json"] = str(asr_json_path)

    try:
        obj = json.loads(asr_json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"ASR fallback failed: invalid JSON output ({exc})."
        return result

    text = (obj.get("text") or "").strip()
    if not text:
        result["note"] = "ASR fallback completed but transcript text is empty."
        return result

    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    text_len = len(text)
    cjk_ratio = round(cjk_count / max(1, text_len), 4)
    result["quality"] = {
        "text_length": text_len,
        "cjk_ratio": cjk_ratio,
        "language": obj.get("language"),
        "language_probability": obj.get("language_probability"),
    }

    transcript_path = outdir / "transcript.txt"
    transcript_path.write_text(text, encoding="utf-8")
    result["transcript_path"] = str(transcript_path)
    result["asr_used"] = True

    # Enhanced quality assessment
    quality_assessment = "high"
    quality_notes = []
    
    if language.lower().startswith("zh"):
        if cjk_ratio < 0.05:
            quality_assessment = "low"
            quality_notes.append(f"Very low CJK ratio ({cjk_ratio}), may indicate poor ASR quality")
            result["note"] = (
                f"ASR transcript quality is LOW for zh (cjk_ratio={cjk_ratio}). "
                "Recommend re-running with --asr-model large-v3 or checking audio quality."
            )
        elif cjk_ratio < 0.08:
            quality_assessment = "medium"
            quality_notes.append(f"Moderate CJK ratio ({cjk_ratio}), acceptable but not optimal")
            if not result["note"]:
                result["note"] = (
                    f"ASR transcript quality is MEDIUM for zh (cjk_ratio={cjk_ratio}). "
                    "Consider re-running with --asr-model large-v3-turbo for better accuracy."
                )
        else:
            quality_notes.append(f"Good CJK ratio ({cjk_ratio}), high confidence")
    
    # Add language detection confidence
    lang_prob = obj.get("language_probability", 0)
    if lang_prob < 0.7:
        quality_notes.append(f"Low language detection confidence ({lang_prob:.2f})")
        if quality_assessment == "high":
            quality_assessment = "medium"
    
    result["quality"]["assessment"] = quality_assessment
    result["quality"]["notes"] = quality_notes

    return result
    if dl.returncode != 0:
        result["note"] = f"ASR fallback failed to download audio: {dl.stderr[-600:]}"
        return result

    audio_files = sorted(outdir.glob("asr_audio.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not audio_files:
        result["note"] = "ASR fallback failed: downloaded audio file not found."
        return result

    audio_path = audio_files[0]
    result["audio_path"] = str(audio_path)

    asr_json_path = outdir / "transcript_asr.json"
    asr_cmd = [
        runner,
        str(audio_path),
        "--model",
        model,
        "--beam-size",
        str(beam_size),
        "--vad",
        "-j",
        "-o",
        str(asr_json_path),
    ]
    if language:
        asr_cmd.extend(["--language", language])

    asr = subprocess.run(asr_cmd, capture_output=True, text=True, check=False)
    if asr.returncode != 0:
        result["note"] = f"ASR fallback failed during transcription: {asr.stderr[-600:]}"
        return result

    if not asr_json_path.exists():
        result["note"] = "ASR fallback failed: transcript_asr.json not created."
        return result

    result["asr_json"] = str(asr_json_path)

    try:
        obj = json.loads(asr_json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"ASR fallback failed: invalid JSON output ({exc})."
        return result

    text = (obj.get("text") or "").strip()
    if not text:
        result["note"] = "ASR fallback completed but transcript text is empty."
        return result

    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    text_len = len(text)
    cjk_ratio = round(cjk_count / max(1, text_len), 4)
    result["quality"] = {
        "text_length": text_len,
        "cjk_ratio": cjk_ratio,
        "language": obj.get("language"),
        "language_probability": obj.get("language_probability"),
    }

    transcript_path = outdir / "transcript.txt"
    transcript_path.write_text(text, encoding="utf-8")
    result["transcript_path"] = str(transcript_path)
    result["asr_used"] = True

    # Enhanced quality assessment
    quality_assessment = "high"
    quality_notes = []
    
    if language.lower().startswith("zh"):
        if cjk_ratio < 0.05:
            quality_assessment = "low"
            quality_notes.append(f"Very low CJK ratio ({cjk_ratio}), may indicate poor ASR quality")
            result["note"] = (
                f"ASR transcript quality is LOW for zh (cjk_ratio={cjk_ratio}). "
                "Recommend re-running with --asr-model large-v3 or checking audio quality."
            )
        elif cjk_ratio < 0.08:
            quality_assessment = "medium"
            quality_notes.append(f"Moderate CJK ratio ({cjk_ratio}), acceptable but not optimal")
            if not result["note"]:
                result["note"] = (
                    f"ASR transcript quality is MEDIUM for zh (cjk_ratio={cjk_ratio}). "
                    "Consider re-running with --asr-model large-v3-turbo for better accuracy."
                )
        else:
            quality_notes.append(f"Good CJK ratio ({cjk_ratio}), high confidence")
    
    # Add language detection confidence
    lang_prob = obj.get("language_probability", 0)
    if lang_prob < 0.7:
        quality_notes.append(f"Low language detection confidence ({lang_prob:.2f})")
        if quality_assessment == "high":
            quality_assessment = "medium"
    
    result["quality"]["assessment"] = quality_assessment
    result["quality"]["notes"] = quality_notes

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and normalize source content.")
    parser.add_argument("--input", required=True, help="URL or topic name")
    parser.add_argument("--outdir", default="./omni_learning_output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds (default: 60, increased for Douyin)")
    parser.add_argument("--retry", type=int, default=2, help="Number of retry attempts for failed fetches (default: 2)")
    parser.add_argument(
        "--asr-fallback",
        action="store_true",
        help="If subtitle extraction fails on media links, run local ASR fallback.",
    )
    parser.add_argument(
        "--asr-model",
        default="large-v3-turbo",
        help="ASR model for faster-whisper runner (default: large-v3-turbo).",
    )
    parser.add_argument(
        "--asr-language",
        default="zh",
        help="ASR language hint, e.g. zh/en. Empty string enables auto-detection.",
    )
    parser.add_argument(
        "--asr-beam-size",
        type=int,
        default=5,
        help="ASR beam size (default: 5).",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    source = args.input.strip()
    manifest: dict[str, object] = {
        "input": source,
        "kind": "url" if is_url(source) else "topic",
        "platform": "unknown",
        "normalized_input": source,
        "files": {},
        "notes": [],
    }

    try:
        if is_url(source):
            platform = detect_platform(source)
            manifest["platform"] = platform

            normalized_source = normalize_source_url(source, platform)
            manifest["normalized_input"] = normalized_source
            if normalized_source != source:
                manifest["notes"].append(
                    f"Normalized URL for {platform}: {normalized_source}"
                )

            # Platform-specific timeout adjustments
            platform_timeout = args.timeout
            if platform == "douyin":
                platform_timeout = max(args.timeout, 90)  # Douyin needs more time
                manifest["notes"].append(f"Using extended timeout ({platform_timeout}s) for Douyin")
            
            # Retry logic for flaky platforms
            source_text = None
            read_url = f"https://r.jina.ai/{normalized_source}"
            last_error = None
            jina_success = False
            
            for attempt in range(max(1, args.retry + 1)):
                try:
                    if attempt > 0:
                        manifest["notes"].append(f"Retry attempt {attempt}/{args.retry}...")
                        import time
                        time.sleep(2 ** attempt)  # Exponential backoff
                    
                    source_text = http_get_text(read_url, platform_timeout)
                    if source_text and len(source_text) > 50:
                        jina_success = True
                        break  # Success
                    elif not source_text:
                        last_error = Exception("Empty response")
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    manifest["notes"].append(f"Attempt {attempt + 1} failed: {exc}")
                    continue
            
            # For Douyin/Xiaohongshu, Jina failure is OK if we have ASR fallback
            if jina_success:
                read_path = outdir / "source_read.md"
                read_path.write_text(source_text, encoding="utf-8")
                manifest["files"]["source_read"] = str(read_path)
                manifest["files"]["read_via"] = read_url
            elif platform in {"douyin", "xiaohongshu"} and args.asr_fallback:
                manifest["notes"].append("Jina Reader failed, but will proceed with MCP + ASR fallback for audio transcription")
            else:
                raise Exception(f"Failed to fetch content after {args.retry + 1} attempts: {last_error}")

            # Platform-specific metadata extraction
            # For Douyin/Xiaohongshu, try MCP first (works even if Jina failed)
            if platform == "bilibili":
                bilibili_meta = fetch_bilibili_metadata(normalized_source, args.timeout)
                bilibili_meta_path = outdir / "bilibili_meta.json"
                bilibili_meta_path.write_text(
                    json.dumps(bilibili_meta, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                manifest["files"]["platform_meta"] = str(bilibili_meta_path)
                if bilibili_meta.get("errors"):
                    manifest["notes"].append(
                        "Bilibili metadata had partial errors: "
                        + "; ".join(bilibili_meta.get("errors") or [])
                    )
            
            elif platform == "douyin":
                # Try MCP for metadata (works independently of Jina)
                if args.asr_fallback:
                    mcp_meta = try_mcp_download(normalized_source, outdir)
                    if mcp_meta.get("video_info"):
                        # Use MCP video info as metadata
                        douyin_meta = {
                            "canonical_url": normalized_source,
                            "video_id": extract_douyin_video_id(normalized_source),
                            "title": mcp_meta["video_info"].get("caption", "Unknown"),
                            "author": mcp_meta["video_info"].get("author"),
                            "source": "MCP",
                        }
                        douyin_meta_path = outdir / "douyin_meta.json"
                        douyin_meta_path.write_text(
                            json.dumps(douyin_meta, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        manifest["files"]["platform_meta"] = str(douyin_meta_path)
                        manifest["notes"].append("Douyin metadata from MCP")
                    else:
                        # Fallback to Jina-based metadata
                        douyin_meta = fetch_douyin_metadata(normalized_source, args.timeout)
                        douyin_meta_path = outdir / "douyin_meta.json"
                        douyin_meta_path.write_text(
                            json.dumps(douyin_meta, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        manifest["files"]["platform_meta"] = str(douyin_meta_path)
                else:
                    douyin_meta = fetch_douyin_metadata(normalized_source, args.timeout)
                    douyin_meta_path = outdir / "douyin_meta.json"
                    douyin_meta_path.write_text(
                        json.dumps(douyin_meta, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    manifest["files"]["platform_meta"] = str(douyin_meta_path)
                
                if douyin_meta.get("errors"):
                    manifest["notes"].append(
                        "Douyin metadata had partial errors: "
                        + "; ".join(douyin_meta.get("errors") or [])
                    )
            
            elif platform == "xiaohongshu":
                xiaohongshu_meta = fetch_xiaohongshu_metadata(normalized_source, args.timeout)
                xiaohongshu_meta_path = outdir / "xiaohongshu_meta.json"
                xiaohongshu_meta_path.write_text(
                    json.dumps(xiaohongshu_meta, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                manifest["files"]["platform_meta"] = str(xiaohongshu_meta_path)
                if xiaohongshu_meta.get("errors"):
                    manifest["notes"].append(
                        "Xiaohongshu metadata had partial errors: "
                        + "; ".join(xiaohongshu_meta.get("errors") or [])
                    )

            if platform in {"bilibili", "douyin", "xiaoyuzhou"}:
                # For Douyin, always try ASR fallback immediately (subtitles rarely available)
                if platform == "douyin":
                    manifest["notes"].append("Douyin platform detected: subtitles typically unavailable, will proceed to ASR fallback.")
                
                subtitle_result = try_extract_subtitles(normalized_source, outdir)
                manifest["files"]["subtitle_files"] = subtitle_result["subtitle_files"]
                manifest["files"]["transcript"] = subtitle_result["transcript_path"]
                if subtitle_result["note"]:
                    manifest["notes"].append(str(subtitle_result["note"]))

                # ASR fallback conditions:
                # 1. No transcript from subtitles AND --asr-fallback flag set
                # 2. Douyin platform (always try ASR)
                should_try_asr = (
                    (not subtitle_result["transcript_path"] and args.asr_fallback) or
                    (platform == "douyin" and args.asr_fallback)
                )
                
                if should_try_asr:
                    manifest["notes"].append("Starting ASR fallback for audio transcription...")
                    asr_result = try_asr_fallback(
                        source_url=normalized_source,
                        outdir=outdir,
                        model=args.asr_model,
                        language=args.asr_language.strip(),
                        beam_size=max(1, args.asr_beam_size),
                    )
                    manifest["files"]["asr_audio"] = asr_result["audio_path"]
                    manifest["files"]["asr_json"] = asr_result["asr_json"]
                    if asr_result["transcript_path"]:
                        manifest["files"]["transcript"] = asr_result["transcript_path"]
                    if asr_result["quality"]:
                        manifest["asr_quality"] = asr_result["quality"]
                    if asr_result["note"]:
                        manifest["notes"].append(str(asr_result["note"]))

                if not manifest["files"].get("transcript") and not args.asr_fallback:
                    manifest["notes"].append(
                        "Transcript missing. Re-run with --asr-fallback for full audio transcription."
                    )

        else:
            manifest["platform"] = "search"
            search_text = ""
            search_url = f"https://s.jina.ai/{quote(source)}"
            try:
                search_text = http_get_text(search_url, args.timeout)
                manifest["files"]["search_via"] = search_url
            except Exception:  # noqa: BLE001
                search_text, fallback_url = fetch_duckduckgo_html(source, args.timeout)
                manifest["files"]["search_via"] = fallback_url
                manifest["notes"].append(
                    "s.jina.ai search unavailable; used DuckDuckGo HTML fallback."
                )

            search_path = outdir / "source_search.md"
            search_path.write_text(search_text, encoding="utf-8")
            manifest["files"]["source_search"] = str(search_path)
            manifest["candidates"] = extract_candidate_urls(search_text, limit=5)
            manifest["notes"].append(
                "Input is a topic name. Please pick or confirm a canonical source link before deep analysis."
            )

    except Exception as exc:  # noqa: BLE001
        manifest["notes"].append(f"Fetch error: {exc}")

    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nManifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
