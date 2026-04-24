#!/usr/bin/env python3
"""
Fetch and normalize source content for omni-link-learning skill.

Supports:
- URL input: fetches source content and metadata for supported platforms
- Topic input: fetches search digest via s.jina.ai or DuckDuckGo HTML
- Media platforms: tries subtitles first, then local ASR fallback

Platform adapters prioritize no-token flows:
- WeChat MP: third-party markdown bridge
- Xiaohongshu: direct HTML + embedded state parsing
- Douyin: headless Chrome + network interception
- X posts: Nitter mirrors
- X bookmarks: Field Theory CLI
- Jike: direct HTML parsing with structured-data fallbacks
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse
from urllib.request import Request, urlopen


PLATFORM_DOMAINS = {
    "bilibili": ("bilibili.com", "b23.tv"),
    "douyin": ("douyin.com", "iesdouyin.com", "v.douyin.com", "m.douyin.com"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com", "www.xiaohongshu.com", "www.xiaohongshu.net"),
    "xiaoyuzhou": ("xiaoyuzhoufm.com",),
    "wechat_mp": ("mp.weixin.qq.com",),
    "x": ("x.com", "twitter.com", "www.x.com", "www.twitter.com"),
    "jike": ("okjike.com", "web.okjike.com", "m.okjike.com"),
}

NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
    "https://nitter.net",
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def is_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_bookmark_query(value: str) -> bool:
    stripped = value.strip().lower()
    return stripped.startswith(("x-bookmarks:", "fieldtheory:", "ft:"))


def extract_bookmark_query(value: str) -> str:
    stripped = value.strip()
    for prefix in ("x-bookmarks:", "fieldtheory:", "ft:"):
        if stripped.lower().startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def detect_platform(value: str) -> str:
    host = urlparse(value).netloc.lower()
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(domain in host for domain in domains):
            return platform
    return "web"


def http_fetch(url: str, timeout: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return {
            "url": resp.geturl(),
            "status": getattr(resp, "status", 200),
            "headers": dict(resp.headers.items()),
            "body": body,
            "text": body.decode(charset, errors="replace"),
        }


def http_get_text(url: str, timeout: int, headers: dict[str, str] | None = None) -> str:
    return http_fetch(url, timeout, headers=headers)["text"]


def http_get_json(url: str, timeout: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return json.loads(http_get_text(url, timeout, headers=headers))


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
    )
    return proc.returncode, proc.stdout, proc.stderr


def curl_get_text(url: str, timeout: int, headers: dict[str, str] | None = None, compressed: bool = True) -> str:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found")

    cmd = [curl, "-L", "--max-time", str(timeout), "-A", UA]
    if compressed:
        cmd.append("--compressed")
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    cmd.append(url)

    code, stdout, stderr = run_command(cmd)
    if code != 0 and stdout.strip():
        return stdout
    if code != 0:
        raise RuntimeError(stderr.strip() or f"curl failed for {url}")
    return stdout


def fetch_duckduckgo_html(query: str, timeout: int) -> tuple[str, str]:
    ddg_url = f"https://duckduckgo.com/html/?q={quote(query)}"
    return http_get_text(ddg_url, timeout), ddg_url


def strip_html_tags(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_subtitle_text(raw: str) -> str:
    lines: list[str] = []
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

    dedup: list[str] = []
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
        if not host or "duckduckgo.com" in host:
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
    subtitle_files: list[Path] = []
    for pattern in ("*.srt", "*.vtt"):
        subtitle_files.extend(outdir.rglob(pattern))
    return sorted(set(subtitle_files))


def try_extract_subtitles(source_url: str, outdir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
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
        result["note"] = "yt-dlp ran but no subtitles found. Consider ASR fallback with --asr-fallback."
        return result

    blocks: list[str] = []
    for path in subtitle_files:
        try:
            cleaned = clean_subtitle_text(path.read_text(encoding="utf-8", errors="replace"))
            if cleaned:
                blocks.append(f"## {path.name}\n\n{cleaned}")
        except Exception as exc:  # noqa: BLE001
            blocks.append(f"## {path.name}\n\n[Failed to parse subtitle: {exc}]")

    transcript = "\n\n".join(blocks).strip()
    if transcript:
        transcript_path = outdir / "transcript.txt"
        transcript_path.write_text(transcript, encoding="utf-8")
        result["transcript_path"] = str(transcript_path)
    elif proc.returncode != 0:
        result["note"] = f"yt-dlp ran but subtitles were unusable: {proc.stderr[-300:]}"
    else:
        result["note"] = "Subtitle files were present but contained no usable text."
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
    parsed = urlparse(url)
    patterns = [
        r"/video/(\d+)",
        r"/note/(\d+)",
        r"modal_id=(\d+)",
        r"aweme_id=(\d+)",
        r"share/video/(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, parsed.path + "?" + parsed.query)
        if m:
            return m.group(1)
    return None


def extract_xiaohongshu_note_id(url: str) -> str | None:
    parsed = urlparse(url)
    patterns = [
        r"/explore/([a-zA-Z0-9]+)",
        r"/discovery/item/([a-zA-Z0-9]+)",
        r"[?&]note_id=([a-zA-Z0-9]+)",
    ]
    text = parsed.path + "?" + parsed.query
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def resolve_short_url(source: str, timeout: int) -> str:
    try:
        return http_fetch(source, timeout, headers=BROWSER_HEADERS)["url"]
    except Exception:
        return source


def normalize_source_url(source: str, platform: str, timeout: int) -> str:
    if platform == "bilibili":
        bvid = extract_bilibili_bvid(source)
        return f"https://www.bilibili.com/video/{bvid}" if bvid else source
    if platform == "douyin":
        resolved = resolve_short_url(source, timeout) if "v.douyin.com" in source or "iesdouyin.com" in source else source
        video_id = extract_douyin_video_id(resolved)
        return f"https://www.douyin.com/video/{video_id}" if video_id else resolved
    if platform == "xiaohongshu":
        resolved = resolve_short_url(source, timeout) if "xhslink.com" in source else source
        note_id = extract_xiaohongshu_note_id(resolved)
        if note_id:
            parsed = urlparse(resolved)
            canonical = f"https://www.xiaohongshu.com/explore/{note_id}"
            if parsed.query:
                canonical = f"{canonical}?{parsed.query}"
            return canonical
        return resolved
    if platform == "x":
        return source.replace("twitter.com", "x.com")
    return source


def sec_to_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}, ()):
            return value
    return None


def coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        if digits:
            try:
                return int(digits)
            except Exception:  # noqa: BLE001
                return None
    return None


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def extract_meta_tags(raw_html: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for attrs in re.findall(r"<meta\s+([^>]+)>", raw_html, flags=re.I):
        name_match = re.search(r'(?:name|property)\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
        content_match = re.search(r'content\s*=\s*["\']([^"\']*)["\']', attrs, flags=re.I)
        if name_match and content_match:
            tags[name_match.group(1).strip().lower()] = html.unescape(content_match.group(1).strip())
    return tags


def html_to_readable_markdown(raw_html: str, source_url: str) -> str:
    meta_tags = extract_meta_tags(raw_html)
    title = first_nonempty(meta_tags.get("og:title"), meta_tags.get("twitter:title"), meta_tags.get("title"))
    description = first_nonempty(meta_tags.get("og:description"), meta_tags.get("description"), meta_tags.get("twitter:description"))

    paragraphs: list[str] = []
    for match in re.findall(r"<p[^>]*>(.*?)</p>", raw_html, flags=re.I | re.S):
        text = strip_html_tags(match)
        if len(text) >= 30:
            paragraphs.append(text)
        if len(paragraphs) >= 20:
            break

    if not paragraphs:
        body_match = re.search(r"<body[^>]*>(.*?)</body>", raw_html, flags=re.I | re.S)
        if body_match:
            body_text = strip_html_tags(body_match.group(1))
            lines = [line.strip() for line in body_text.splitlines() if len(line.strip()) >= 30]
            paragraphs = lines[:20]

    parts: list[str] = [f"# {title or '网页内容'}", ""]
    parts.append(f"- 链接: {source_url}")
    parts.append("")
    if description:
        parts.append("## 摘要")
        parts.append("")
        parts.append(description)
        parts.append("")
    if paragraphs:
        parts.append("## 正文")
        parts.append("")
        parts.extend(paragraphs)
        parts.append("")

    return "\n".join(parts).strip() + "\n"


def extract_json_blob_after_anchor(text: str, anchors: list[str]) -> Any | None:
    for anchor in anchors:
        start = text.find(anchor)
        if start < 0:
            continue
        start = text.find("=", start)
        if start < 0:
            continue
        i = start + 1
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text) or text[i] not in "[{":
            continue

        opening = text[i]
        closing = "]" if opening == "[" else "}"
        depth = 0
        in_string = False
        escaped = False
        quote_char = ""
        for j in range(i, len(text)):
            ch = text[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote_char:
                    in_string = False
            else:
                if ch in {'"', "'"}:
                    in_string = True
                    quote_char = ch
                elif ch == opening:
                    depth += 1
                elif ch == closing:
                    depth -= 1
                    if depth == 0:
                        snippet = text[i:j + 1]
                        try:
                            return json.loads(snippet)
                        except Exception:
                            break
    return None


def walk_json(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


def extract_urls_from_obj(obj: Any, allow_images: bool = True, allow_videos: bool = True) -> list[str]:
    urls: list[str] = []
    for node in walk_json(obj):
        for key, value in node.items():
            if isinstance(value, str) and value.startswith("http"):
                lower_key = key.lower()
                if not allow_images and any(part in lower_key for part in ("image", "cover", "poster")):
                    continue
                if not allow_videos and any(part in lower_key for part in ("video", "play", "stream")):
                    continue
                urls.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.startswith("http"):
                        urls.append(item)
    return dedupe_keep_order(urls)


def fetch_bilibili_metadata(source_url: str, timeout: int) -> dict[str, Any]:
    bvid = extract_bilibili_bvid(source_url)
    meta: dict[str, Any] = {
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
            headers={"User-Agent": UA},
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
                headers={"User-Agent": UA},
            )
            if tag_resp.get("code") == 0:
                tags = [x.get("tag_name") for x in (tag_resp.get("data") or []) if x.get("tag_name")]
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"tag api failed: {exc}")
    meta["tags"] = tags

    chapters: list[dict[str, Any]] = []
    subtitle_tracks: list[dict[str, Any]] = []
    need_login_subtitle = None
    if aid and cid:
        try:
            player = http_get_json(
                f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}",
                timeout,
                headers={"User-Agent": UA},
            )
            if player.get("code") == 0:
                pdata = player.get("data") or {}
                for item in pdata.get("view_points") or []:
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

                subtitle = pdata.get("subtitle") or {}
                need_login_subtitle = pdata.get("need_login_subtitle")
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


def sanitize_wechat_markdown(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").splitlines()
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("!["):
            start = i
            break
        if stripped.startswith("# ") or stripped.startswith("## "):
            start = i
            break
        if stripped.endswith("==================="):
            start = i
            break
    cleaned = "\n".join(lines[start:]).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def extract_title_from_markdown(markdown: str) -> str | None:
    lines = [line.rstrip() for line in markdown.splitlines() if line.strip()]
    if not lines:
        return None
    if lines[0].startswith("#"):
        return lines[0].lstrip("#").strip()
    for i in range(len(lines) - 1):
        if set(lines[i + 1]) == {"="} and lines[i].strip():
            return lines[i].strip()
    return lines[0].strip()


def fetch_wechat_article(source_url: str, timeout: int) -> dict[str, Any]:
    api_url = (
        "https://down.mptext.top/api/public/v1/download"
        f"?url={quote(source_url, safe='')}&format=markdown"
    )
    result: dict[str, Any] = {
        "markdown": "",
        "meta": {
            "canonical_url": source_url,
            "source": "down.mptext.top",
            "api_url": api_url,
            "errors": [],
        },
    }
    try:
        markdown = sanitize_wechat_markdown(http_get_text(api_url, timeout, headers=BROWSER_HEADERS))
        result["markdown"] = markdown
        result["meta"]["title"] = extract_title_from_markdown(markdown)
        author_match = re.search(r"原创\s+([^\n]+)", markdown)
        if author_match:
            result["meta"]["author"] = author_match.group(1).strip()
    except Exception as exc:  # noqa: BLE001
        result["meta"]["errors"].append(f"WeChat article fetch failed: {exc}")
    return result


def extract_xiaohongshu_note_from_state(state: Any) -> dict[str, Any] | None:
    if not state:
        return None

    for node in walk_json(state):
        detail_map = node.get("noteDetailMap")
        if isinstance(detail_map, dict) and detail_map:
            for value in detail_map.values():
                if isinstance(value, dict):
                    return value

    best_candidate = None
    for node in walk_json(state):
        if not isinstance(node, dict):
            continue
        keys = {key.lower() for key in node.keys()}
        if "noteid" in keys or "note_id" in keys:
            if {"title", "desc"} & keys or {"imagelist", "interactinfo", "user"} & keys:
                best_candidate = node
                break
    return best_candidate


def render_xiaohongshu_markdown(meta: dict[str, Any]) -> str:
    parts = [f"# {meta.get('title') or '小红书笔记'}", ""]
    if meta.get("author"):
        parts.append(f"- 作者: {meta['author']}")
    if meta.get("published_at"):
        parts.append(f"- 发布时间: {meta['published_at']}")
    stats = []
    for label, key in [("点赞", "like_count"), ("收藏", "collect_count"), ("评论", "comment_count"), ("分享", "share_count")]:
        value = meta.get(key)
        if value is not None:
            stats.append(f"{label} {value}")
    if stats:
        parts.append(f"- 互动: {' | '.join(stats)}")
    if meta.get("canonical_url"):
        parts.append(f"- 链接: {meta['canonical_url']}")
    parts.append("")
    if meta.get("desc"):
        parts.append("## 正文")
        parts.append("")
        parts.append(meta["desc"])
        parts.append("")
    image_urls = meta.get("image_urls") or []
    if image_urls:
        parts.append("## 图片")
        parts.append("")
        parts.extend(f"- {url}" for url in image_urls)
        parts.append("")
    if meta.get("video_url"):
        parts.append("## 视频")
        parts.append("")
        parts.append(f"- 直链: {meta['video_url']}")
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def fetch_xiaohongshu_note(source_url: str, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "markdown": "",
        "meta": {
            "canonical_url": source_url,
            "note_id": extract_xiaohongshu_note_id(source_url),
            "source": "direct_html",
            "errors": [],
        },
    }

    try:
        response = http_fetch(source_url, timeout, headers={**BROWSER_HEADERS, "Referer": "https://www.xiaohongshu.com/"})
        raw_html = response["text"]
        final_url = response["url"]
        meta_tags = extract_meta_tags(raw_html)
        state = extract_json_blob_after_anchor(
            raw_html,
            [
                "window.__INITIAL_STATE__",
                "window.__INITIAL_SSR_STATE__",
                "__INITIAL_STATE__",
            ],
        )
        note = extract_xiaohongshu_note_from_state(state) or {}

        author_obj = first_nonempty(note.get("user"), note.get("author"), note.get("userInfo")) or {}
        interact = first_nonempty(note.get("interactInfo"), note.get("interaction"), note.get("stats")) or {}

        image_urls = extract_urls_from_obj(note, allow_images=True, allow_videos=False)
        image_urls = [url for url in image_urls if any(ext in url for ext in ("image", "jpg", "jpeg", "png", "webp", "heic"))]

        video_url = None
        for url in extract_urls_from_obj(note, allow_images=False, allow_videos=True):
            if any(token in url.lower() for token in ("mp4", "m3u8", "video", "stream")):
                video_url = url
                break

        meta = result["meta"]
        meta["canonical_url"] = final_url
        meta["note_id"] = extract_xiaohongshu_note_id(final_url) or meta["note_id"]
        meta["title"] = first_nonempty(note.get("title"), meta_tags.get("og:title"), meta_tags.get("title"))
        meta["desc"] = first_nonempty(note.get("desc"), note.get("description"), meta_tags.get("description"))
        meta["author"] = first_nonempty(
            author_obj.get("nickname"),
            author_obj.get("nickName"),
            author_obj.get("name"),
            meta_tags.get("og:site_name"),
        )
        meta["published_at"] = first_nonempty(note.get("time"), note.get("publishTime"))
        meta["like_count"] = coerce_int(first_nonempty(interact.get("likedCount"), note.get("likedCount")))
        meta["collect_count"] = coerce_int(first_nonempty(interact.get("collectedCount"), note.get("collectedCount")))
        meta["comment_count"] = coerce_int(first_nonempty(interact.get("commentCount"), note.get("commentCount")))
        meta["share_count"] = coerce_int(first_nonempty(interact.get("shareCount"), note.get("shareCount")))
        meta["image_urls"] = dedupe_keep_order(image_urls)
        meta["video_url"] = video_url
        meta["raw_state_found"] = bool(state)
        if "/404" in final_url or "暂时无法浏览" in final_url:
            meta["errors"].append("Xiaohongshu redirected to an unavailable/404 page.")
        elif not meta.get("video_url"):
            browser_capture = fetch_xiaohongshu_video_via_browser(final_url, timeout)
            if browser_capture.get("video_url"):
                meta["video_url"] = browser_capture["video_url"]
                meta["browser_capture"] = True
            elif browser_capture.get("errors"):
                meta["browser_capture_errors"] = browser_capture["errors"]

        result["markdown"] = render_xiaohongshu_markdown(meta)
    except Exception as exc:  # noqa: BLE001
        result["meta"]["errors"].append(f"Xiaohongshu fetch failed: {exc}")

    return result


def render_jike_markdown(meta: dict[str, Any]) -> str:
    title = meta.get("title") or "即刻内容"
    parts = [f"# {title}", ""]
    if meta.get("author"):
        parts.append(f"- 作者: {meta['author']}")
    stats = []
    for label, key in [("点赞", "like_count"), ("评论", "comment_count"), ("转发", "repost_count")]:
        if meta.get(key) is not None:
            stats.append(f"{label} {meta[key]}")
    if stats:
        parts.append(f"- 互动: {' | '.join(stats)}")
    if meta.get("canonical_url"):
        parts.append(f"- 链接: {meta['canonical_url']}")
    parts.append("")
    if meta.get("content"):
        parts.append("## 正文")
        parts.append("")
        parts.append(meta["content"])
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def fetch_jike_post(source_url: str, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "markdown": "",
        "meta": {
            "canonical_url": source_url,
            "source": "direct_html",
            "errors": [],
            "strategies_tried": ["curl_parse"],
        },
    }
    try:
        response = http_fetch(source_url, timeout, headers=BROWSER_HEADERS)
        raw_html = response["text"]
        final_url = response["url"]
        meta_tags = extract_meta_tags(raw_html)
        state = extract_json_blob_after_anchor(
            raw_html,
            ["window.__INITIAL_STATE__", "__NEXT_DATA__", "window.__NUXT__"],
        )

        content = first_nonempty(meta_tags.get("description"), meta_tags.get("og:description"))
        title = first_nonempty(meta_tags.get("og:title"), meta_tags.get("title"))
        author = None
        like_count = None
        comment_count = None
        repost_count = None

        if state:
            for node in walk_json(state):
                if not isinstance(node, dict):
                    continue
                if not title and isinstance(node.get("title"), str):
                    title = node.get("title")
                if not content and isinstance(node.get("content"), str):
                    content = node.get("content")
                if not author:
                    author = first_nonempty(
                        (node.get("user") or {}).get("nickname") if isinstance(node.get("user"), dict) else None,
                        (node.get("author") or {}).get("nickname") if isinstance(node.get("author"), dict) else None,
                        node.get("authorName"),
                    )
                like_count = like_count or coerce_int(first_nonempty(node.get("likeCount"), node.get("likedCount")))
                comment_count = comment_count or coerce_int(node.get("commentCount"))
                repost_count = repost_count or coerce_int(first_nonempty(node.get("repostCount"), node.get("shareCount")))

        if not like_count:
            m = re.search(r'"(?:likeCount|likedCount)"\s*:\s*(\d+)', raw_html)
            if m:
                like_count = int(m.group(1))
        if not comment_count:
            m = re.search(r'"commentCount"\s*:\s*(\d+)', raw_html)
            if m:
                comment_count = int(m.group(1))
        if not repost_count:
            m = re.search(r'"(?:repostCount|shareCount)"\s*:\s*(\d+)', raw_html)
            if m:
                repost_count = int(m.group(1))

        meta = result["meta"]
        meta["canonical_url"] = final_url
        meta["title"] = title
        meta["content"] = content
        meta["author"] = author
        meta["like_count"] = like_count
        meta["comment_count"] = comment_count
        meta["repost_count"] = repost_count
        meta["raw_state_found"] = bool(state)
        result["markdown"] = render_jike_markdown(meta)
    except Exception as exc:  # noqa: BLE001
        result["meta"]["errors"].append(f"Jike fetch failed: {exc}")
        try:
            read_url = f"https://r.jina.ai/{source_url}"
            result["markdown"] = http_get_text(read_url, timeout)
            result["meta"]["source"] = "r.jina.ai"
            result["meta"]["strategies_tried"].append("jina_reader")
        except Exception as inner_exc:  # noqa: BLE001
            result["meta"]["errors"].append(f"Jina fallback failed: {inner_exc}")
    return result


def to_nitter_urls(source_url: str) -> list[str]:
    parsed = urlparse(source_url.replace("twitter.com", "x.com"))
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    suffix = f"{path}{query}"
    return [f"{instance}{suffix}" for instance in NITTER_INSTANCES]


def render_x_markdown(meta: dict[str, Any]) -> str:
    title = meta.get("title") or meta.get("author") or "X 内容"
    parts = [f"# {title}", ""]
    if meta.get("author"):
        parts.append(f"- 作者: {meta['author']}")
    if meta.get("handle"):
        parts.append(f"- 账号: {meta['handle']}")
    if meta.get("published_at"):
        parts.append(f"- 发布时间: {meta['published_at']}")
    if meta.get("canonical_url"):
        parts.append(f"- 链接: {meta['canonical_url']}")
    media_urls = meta.get("media_urls") or []
    if media_urls:
        parts.append(f"- 媒体数: {len(media_urls)}")
    parts.append("")
    if meta.get("content"):
        parts.append("## 正文")
        parts.append("")
        parts.append(meta["content"])
        parts.append("")
    if media_urls:
        parts.append("## 媒体")
        parts.append("")
        parts.extend(f"- {url}" for url in media_urls)
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def fetch_x_via_nitter(source_url: str, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "markdown": "",
        "meta": {
            "canonical_url": source_url,
            "source": "nitter",
            "errors": [],
            "instances_tried": [],
        },
    }

    for candidate in to_nitter_urls(source_url):
        result["meta"]["instances_tried"].append(candidate)
        try:
            response = http_fetch(candidate, timeout, headers=BROWSER_HEADERS)
            raw_html = response["text"]
            if len(raw_html) < 200 or "Bad Gateway" in raw_html or "Just a moment" in raw_html:
                continue

            meta_tags = extract_meta_tags(raw_html)
            content_match = re.search(
                r'<div class="tweet-content[^"]*">(.*?)</div>',
                raw_html,
                flags=re.S,
            )
            content = strip_html_tags(content_match.group(1)) if content_match else None
            if not content:
                content = first_nonempty(meta_tags.get("description"), meta_tags.get("og:description"))

            author_match = re.search(r'<a class="fullname"[^>]*>(.*?)</a>', raw_html, flags=re.S)
            handle_match = re.search(r'<a class="username"[^>]*>(.*?)</a>', raw_html, flags=re.S)
            date_match = re.search(r'<span class="tweet-date"[^>]*>\s*<a[^>]*title="([^"]+)"', raw_html)

            media_urls = re.findall(r'(https://(?:pbs|video)\.twimg\.com/[^\s"\']+)', raw_html)
            media_urls = dedupe_keep_order(media_urls)

            meta = result["meta"]
            meta["nitter_url"] = candidate
            meta["title"] = first_nonempty(meta_tags.get("og:title"), meta_tags.get("title"))
            meta["content"] = content
            meta["author"] = strip_html_tags(author_match.group(1)) if author_match else None
            meta["handle"] = strip_html_tags(handle_match.group(1)) if handle_match else None
            meta["published_at"] = date_match.group(1) if date_match else None
            meta["media_urls"] = media_urls
            result["markdown"] = render_x_markdown(meta)
            return result
        except Exception as exc:  # noqa: BLE001
            result["meta"]["errors"].append(f"{candidate}: {exc}")

    result["meta"]["errors"].append("No Nitter instance returned usable content.")
    browser_result = fetch_x_via_browser(source_url, timeout)
    if browser_result.get("markdown"):
        browser_result["meta"]["errors"] = result["meta"]["errors"] + browser_result["meta"].get("errors", [])
        return browser_result
    return result


def fetch_x_via_browser(source_url: str, timeout: int) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parent / "x_capture.mjs"
    result: dict[str, Any] = {
        "markdown": "",
        "meta": {
            "canonical_url": source_url,
            "source": "browser",
            "errors": [],
        },
    }
    if not script_path.exists():
        result["meta"]["errors"].append(f"Missing X browser capture script: {script_path}")
        return result

    node = shutil.which("node")
    if not node:
        result["meta"]["errors"].append("Node.js not found; cannot run X browser capture.")
        return result

    code, stdout, stderr = run_command(
        [node, str(script_path), "--url", source_url, "--timeout", str(max(15000, timeout * 1000))],
        cwd=find_playwright_script_dir(),
    )
    if code != 0:
        result["meta"]["errors"].append(f"X browser capture failed: {stderr[-400:]}")
        return result

    try:
        payload = json.loads(stdout.strip())
    except Exception as exc:  # noqa: BLE001
        result["meta"]["errors"].append(f"Invalid X browser capture JSON: {exc}")
        return result

    article_text = (payload.get("article_text") or "").strip()
    if not article_text:
        result["meta"]["errors"].append("X browser capture returned no article text.")
        return result

    meta = result["meta"]
    meta["canonical_url"] = first_nonempty(payload.get("final_url"), source_url)
    meta["title"] = payload.get("title")
    meta["author"] = payload.get("author")
    meta["handle"] = payload.get("handle")
    meta["published_at"] = payload.get("published_at")
    meta["media_urls"] = payload.get("media_urls") or []
    meta["source"] = "browser"
    meta["content"] = article_text
    result["markdown"] = render_x_markdown(meta)
    return result


def fetch_xiaohongshu_video_via_browser(source_url: str, timeout: int) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parent / "xhs_capture.mjs"
    result: dict[str, Any] = {"video_url": None, "errors": []}
    if not script_path.exists():
        result["errors"].append(f"Missing XHS browser capture script: {script_path}")
        return result

    node = shutil.which("node")
    if not node:
        result["errors"].append("Node.js not found; cannot run XHS browser capture.")
        return result

    code, stdout, stderr = run_command(
        [node, str(script_path), "--url", source_url, "--timeout", str(max(15000, timeout * 1000))],
        cwd=find_playwright_script_dir(),
    )
    if code != 0:
        result["errors"].append(f"XHS browser capture failed: {stderr[-400:]}")
        return result

    try:
        payload = json.loads(stdout.strip())
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"Invalid XHS browser capture JSON: {exc}")
        return result

    result["video_url"] = payload.get("video_url")
    if payload.get("errors"):
        result["errors"].extend(payload["errors"])
    return result


def find_playwright_script_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def fetch_douyin_detail_via_browser(source_url: str, timeout: int) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parent / "douyin_capture.mjs"
    result: dict[str, Any] = {
        "meta": {
            "canonical_url": source_url,
            "source": "playwright",
            "errors": [],
        },
        "markdown": "",
        "play_url": None,
        "music_url": None,
        "cover_url": None,
    }
    if not script_path.exists():
        result["meta"]["errors"].append(f"Missing browser capture script: {script_path}")
        return result

    node = shutil.which("node")
    if not node:
        result["meta"]["errors"].append("Node.js not found; cannot run Douyin browser capture.")
        return result

    code, stdout, stderr = run_command(
        [node, str(script_path), "--url", source_url, "--timeout", str(max(15000, timeout * 1000))],
        cwd=find_playwright_script_dir(),
    )
    if code != 0:
        result["meta"]["errors"].append(
            "Douyin browser capture failed. "
            "Ensure `npm install` has been run to install Playwright. "
            f"stderr={stderr[-400:]}"
        )
        return result

    try:
        payload = json.loads(stdout.strip())
    except Exception as exc:  # noqa: BLE001
        result["meta"]["errors"].append(f"Invalid Douyin browser capture JSON: {exc}")
        return result

    stats = payload.get("statistics") or {}
    meta = result["meta"]
    meta["canonical_url"] = first_nonempty(payload.get("final_url"), source_url)
    meta["aweme_id"] = payload.get("aweme_id")
    meta["title"] = first_nonempty(payload.get("title"), payload.get("desc"))
    meta["author"] = payload.get("author")
    meta["author_uid"] = payload.get("author_uid")
    meta["published_at"] = payload.get("create_time")
    meta["like_count"] = coerce_int(stats.get("digg_count"))
    meta["comment_count"] = coerce_int(stats.get("comment_count"))
    meta["share_count"] = coerce_int(stats.get("share_count"))
    meta["collect_count"] = coerce_int(stats.get("collect_count"))
    meta["captured_api_url"] = payload.get("captured_api_url")
    meta["cover_url"] = payload.get("cover_url")
    meta["play_url"] = payload.get("play_url")
    meta["music_url"] = payload.get("music_url")
    meta["browser_capture"] = True

    result["play_url"] = payload.get("play_url")
    result["music_url"] = payload.get("music_url")
    result["cover_url"] = payload.get("cover_url")

    lines = [f"# {meta.get('title') or '抖音视频'}", ""]
    if meta.get("author"):
        lines.append(f"- 作者: {meta['author']}")
    stats_line = []
    for label, key in [("点赞", "like_count"), ("评论", "comment_count"), ("收藏", "collect_count"), ("分享", "share_count")]:
        if meta.get(key) is not None:
            stats_line.append(f"{label} {meta[key]}")
    if stats_line:
        lines.append(f"- 互动: {' | '.join(stats_line)}")
    if meta.get("canonical_url"):
        lines.append(f"- 链接: {meta['canonical_url']}")
    if result["play_url"]:
        lines.append(f"- 无水印视频: {result['play_url']}")
    lines.append("")
    if payload.get("desc"):
        lines.append("## 文案")
        lines.append("")
        lines.append(payload["desc"])
        lines.append("")
    result["markdown"] = "\n".join(lines).strip() + "\n"
    return result


def try_fieldtheory_query(query: str, outdir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "markdown": "",
        "meta": {
            "platform": "x_bookmarks",
            "query": query,
            "source": "fieldtheory",
            "errors": [],
        },
    }

    fieldtheory = shutil.which("ft") or shutil.which("fieldtheory")
    base_cmd = [fieldtheory] if fieldtheory else ["npx", "-y", "fieldtheory"]

    code, stdout, stderr = run_command(base_cmd + ["status"], cwd=outdir)
    status_text = (stdout or stderr).strip()
    if code != 0 and "No bookmarks synced yet" not in status_text:
        result["meta"]["errors"].append(f"Field Theory status failed: {status_text[-300:]}")

    if "No bookmarks synced yet" in status_text:
        result["markdown"] = (
            "# X 书签\n\n"
            "Field Theory 已安装，但本机还没有同步书签。\n\n"
            "请先在浏览器登录 x.com，然后运行：\n\n"
            "```bash\nft sync\n```\n"
        )
        result["meta"]["needs_sync"] = True
        return result

    code, stdout, stderr = run_command(base_cmd + ["search", query, "--limit", "10"], cwd=outdir)
    if code != 0:
        result["meta"]["errors"].append(f"Field Theory search failed: {stderr[-300:]}")
        return result

    result["markdown"] = f"# X 书签搜索\n\n- 查询: {query}\n\n```\n{stdout.strip()}\n```\n"
    return result


def find_fw_transcribe_runner() -> str | None:
    repo_runner = Path(__file__).resolve().parent / "transcribe_local.py"
    if repo_runner.exists():
        return str(repo_runner)

    local_runner = Path.home() / ".codex/skills/faster-whisper/scripts/transcribe"
    if local_runner.exists() and os.access(local_runner, os.X_OK):
        return str(local_runner)
    return shutil.which("transcribe")


def build_media_download_jobs(source_url: str, platform: str, timeout: int) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if platform == "douyin":
        detail = fetch_douyin_detail_via_browser(source_url, timeout)
        if detail.get("play_url"):
            jobs.append(
                {
                    "url": detail["play_url"],
                    "label": "douyin_play_url",
                    "headers": {"Referer": "https://www.douyin.com/"},
                }
            )
        if detail.get("music_url"):
            jobs.append(
                {
                    "url": detail["music_url"],
                    "label": "douyin_music_url",
                    "headers": {"Referer": "https://www.douyin.com/"},
                }
            )
        jobs.append(
            {
                "url": source_url,
                "label": "douyin_page",
                "headers": {},
                "cookies_from_browser": "chrome",
            }
        )
    elif platform == "xiaohongshu":
        note = fetch_xiaohongshu_note(source_url, timeout)
        video_url = (note.get("meta") or {}).get("video_url")
        if video_url:
            jobs.append(
                {
                    "url": video_url,
                    "label": "xiaohongshu_video_url",
                    "headers": {"Referer": "https://www.xiaohongshu.com/"},
                    "cookies_from_browser": "chrome",
                }
            )
        jobs.append(
            {
                "url": source_url,
                "label": "xiaohongshu_page",
                "headers": {"Referer": "https://www.xiaohongshu.com/"},
                "cookies_from_browser": "chrome",
            }
        )
    else:
        jobs.append({"url": source_url, "label": f"{platform}_page", "headers": {}})
    return jobs


def try_asr_fallback(
    source_url: str,
    outdir: Path,
    model: str,
    language: str,
    beam_size: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
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

    platform = detect_platform(source_url)
    ffmpeg_available = bool(shutil.which("ffmpeg"))
    media_pattern = outdir / ("asr_audio.%(ext)s" if ffmpeg_available else "asr_media.%(ext)s")
    jobs = build_media_download_jobs(source_url, platform, timeout=90 if platform == "douyin" else 45)
    media_path: str | None = None
    last_error = None

    for job in jobs:
        cmd = [yt_dlp, "--no-playlist", "--no-warnings", "-o", str(media_pattern)]
        if ffmpeg_available:
            cmd[1:1] = ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        if job.get("cookies_from_browser"):
            cmd.extend(["--cookies-from-browser", job["cookies_from_browser"]])
        for key, value in (job.get("headers") or {}).items():
            cmd.extend(["--add-header", f"{key}: {value}"])
        cmd.append(job["url"])

        result["download_attempts"].append(f"Trying {job['label']}: {job['url']}")
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            pattern_prefix = "asr_audio." if ffmpeg_available else "asr_media."
            media_files = sorted(outdir.glob(f"{pattern_prefix}*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if media_files:
                media_path = str(media_files[0])
                result["download_attempts"].append(f"Success {job['label']}: {media_path}")
                break
            last_error = "Download succeeded but media file was not found."
        else:
            last_error = proc.stderr[-500:] if proc.stderr else "Unknown yt-dlp error"
            result["download_attempts"].append(f"Failed {job['label']}: {last_error[:220]}")

    if not media_path:
        result["note"] = f"ASR fallback failed to download media: {last_error}"
        return result

    result["audio_path"] = media_path

    asr_json_path = outdir / "transcript_asr.json"
    asr_cmd = [
        runner,
        media_path,
        "--model",
        model,
        "--beam-size",
        str(max(1, beam_size)),
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

    assessment = "high"
    notes: list[str] = []
    if language.lower().startswith("zh"):
        if cjk_ratio < 0.05:
            assessment = "low"
            notes.append(f"Very low CJK ratio ({cjk_ratio})")
        elif cjk_ratio < 0.08:
            assessment = "medium"
            notes.append(f"Moderate CJK ratio ({cjk_ratio})")
        else:
            notes.append(f"Good CJK ratio ({cjk_ratio})")

    lang_prob = obj.get("language_probability", 0) or 0
    if lang_prob < 0.7:
        notes.append(f"Low language detection confidence ({lang_prob:.2f})")
        if assessment == "high":
            assessment = "medium"
    result["quality"]["assessment"] = assessment
    result["quality"]["notes"] = notes
    return result


def write_platform_meta(outdir: Path, filename: str, data: dict[str, Any]) -> str:
    path = outdir / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def fetch_generic_web(source_url: str, timeout: int) -> tuple[str, str]:
    read_url = f"https://r.jina.ai/{source_url}"
    try:
        return http_get_text(read_url, timeout), read_url
    except Exception:
        pass

    try:
        return curl_get_text(read_url, timeout), read_url
    except Exception:
        pass

    raw_html = None
    try:
        raw_html = curl_get_text(source_url, timeout, headers=BROWSER_HEADERS)
    except Exception:
        try:
            raw_html = http_get_text(source_url, timeout, headers=BROWSER_HEADERS)
        except Exception as exc:
            raise exc

    return html_to_readable_markdown(raw_html, source_url), "direct_html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and normalize source content.")
    parser.add_argument("--input", required=True, help="URL, topic name, or x-bookmarks query")
    parser.add_argument("--outdir", default="./omni_learning_output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds")
    parser.add_argument("--retry", type=int, default=2, help="Number of retry attempts for flaky fetches")
    parser.add_argument("--asr-fallback", action="store_true", help="Use local ASR when subtitles are missing")
    parser.add_argument("--asr-model", default="large-v3-turbo", help="ASR model")
    parser.add_argument("--asr-language", default="zh", help="ASR language hint, e.g. zh/en")
    parser.add_argument("--asr-beam-size", type=int, default=5, help="ASR beam size")
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    source = args.input.strip()
    manifest: dict[str, Any] = {
        "input": source,
        "kind": "url" if is_url(source) else ("bookmark_query" if is_bookmark_query(source) else "topic"),
        "platform": "unknown",
        "normalized_input": source,
        "files": {},
        "notes": [],
    }

    try:
        if is_bookmark_query(source):
            query = extract_bookmark_query(source)
            manifest["platform"] = "x_bookmarks"
            manifest["normalized_input"] = query
            bookmark_result = try_fieldtheory_query(query, outdir)
            read_path = outdir / "source_read.md"
            read_path.write_text(bookmark_result["markdown"], encoding="utf-8")
            manifest["files"]["source_read"] = str(read_path)
            meta_path = write_platform_meta(outdir, "x_bookmarks_meta.json", bookmark_result["meta"])
            manifest["files"]["platform_meta"] = meta_path
            if bookmark_result["meta"].get("errors"):
                manifest["notes"].append("; ".join(bookmark_result["meta"]["errors"]))

        elif is_url(source):
            platform = detect_platform(source)
            manifest["platform"] = platform
            normalized_source = normalize_source_url(source, platform, args.timeout)
            manifest["normalized_input"] = normalized_source
            if normalized_source != source:
                manifest["notes"].append(f"Normalized URL for {platform}: {normalized_source}")

            source_read_text: str | None = None
            read_via: str | None = None
            platform_meta: dict[str, Any] | None = None

            if platform == "wechat_mp":
                fetched = fetch_wechat_article(normalized_source, args.timeout)
                source_read_text = fetched["markdown"]
                platform_meta = fetched["meta"]
                read_via = platform_meta.get("api_url")

            elif platform == "xiaohongshu":
                fetched = fetch_xiaohongshu_note(normalized_source, args.timeout)
                source_read_text = fetched["markdown"]
                platform_meta = fetched["meta"]
                read_via = platform_meta.get("source")

            elif platform == "douyin":
                fetched = fetch_douyin_detail_via_browser(normalized_source, args.timeout)
                source_read_text = fetched["markdown"]
                platform_meta = fetched["meta"]
                read_via = "playwright"

            elif platform == "x":
                fetched = fetch_x_via_nitter(normalized_source, args.timeout)
                source_read_text = fetched["markdown"]
                platform_meta = fetched["meta"]
                read_via = platform_meta.get("nitter_url")

            elif platform == "jike":
                fetched = fetch_jike_post(normalized_source, args.timeout)
                source_read_text = fetched["markdown"]
                platform_meta = fetched["meta"]
                read_via = platform_meta.get("source")

            else:
                # Generic web route and bilibili/xiaoyuzhou content read.
                last_error = None
                for attempt in range(max(1, args.retry + 1)):
                    try:
                        if attempt > 0:
                            time.sleep(2 ** attempt)
                        source_read_text, read_via = fetch_generic_web(normalized_source, args.timeout)
                        if source_read_text and len(source_read_text) > 40:
                            break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                if not source_read_text:
                    raise Exception(f"Failed to fetch content after retries: {last_error}")

            if source_read_text:
                read_path = outdir / "source_read.md"
                read_path.write_text(source_read_text, encoding="utf-8")
                manifest["files"]["source_read"] = str(read_path)
                if read_via:
                    manifest["files"]["read_via"] = read_via

            if platform == "bilibili":
                platform_meta = fetch_bilibili_metadata(normalized_source, args.timeout)
                meta_path = write_platform_meta(outdir, "bilibili_meta.json", platform_meta)
                manifest["files"]["platform_meta"] = meta_path
            elif platform == "douyin":
                platform_meta = platform_meta or {"canonical_url": normalized_source, "errors": ["No Douyin metadata captured"]}
                meta_path = write_platform_meta(outdir, "douyin_meta.json", platform_meta)
                manifest["files"]["platform_meta"] = meta_path
            elif platform == "xiaohongshu":
                platform_meta = platform_meta or {"canonical_url": normalized_source, "errors": ["No Xiaohongshu metadata captured"]}
                meta_path = write_platform_meta(outdir, "xiaohongshu_meta.json", platform_meta)
                manifest["files"]["platform_meta"] = meta_path
            elif platform == "wechat_mp":
                meta_path = write_platform_meta(outdir, "wechat_mp_meta.json", platform_meta or {})
                manifest["files"]["platform_meta"] = meta_path
            elif platform == "x":
                meta_path = write_platform_meta(outdir, "x_meta.json", platform_meta or {})
                manifest["files"]["platform_meta"] = meta_path
            elif platform == "jike":
                meta_path = write_platform_meta(outdir, "jike_meta.json", platform_meta or {})
                manifest["files"]["platform_meta"] = meta_path

            if platform_meta and platform_meta.get("errors"):
                manifest["notes"].append("; ".join(platform_meta["errors"]))

            if platform in {"bilibili", "douyin", "xiaoyuzhou", "xiaohongshu"}:
                subtitle_result = try_extract_subtitles(normalized_source, outdir)
                manifest["files"]["subtitle_files"] = subtitle_result["subtitle_files"]
                manifest["files"]["transcript"] = subtitle_result["transcript_path"]
                if subtitle_result["note"]:
                    manifest["notes"].append(str(subtitle_result["note"]))

                should_try_asr = (
                    args.asr_fallback
                    and (
                        not subtitle_result["transcript_path"]
                        or platform in {"douyin", "xiaohongshu"}
                    )
                )
                if should_try_asr:
                    asr_result = try_asr_fallback(
                        source_url=normalized_source,
                        outdir=outdir,
                        model=args.asr_model,
                        language=args.asr_language.strip(),
                        beam_size=args.asr_beam_size,
                    )
                    manifest["files"]["asr_audio"] = asr_result["audio_path"]
                    manifest["files"]["asr_json"] = asr_result["asr_json"]
                    if asr_result["transcript_path"]:
                        manifest["files"]["transcript"] = asr_result["transcript_path"]
                    if asr_result["quality"]:
                        manifest["asr_quality"] = asr_result["quality"]
                    if asr_result["download_attempts"]:
                        manifest["download_attempts"] = asr_result["download_attempts"]
                    if asr_result["note"]:
                        manifest["notes"].append(str(asr_result["note"]))

                if not manifest["files"].get("transcript") and not args.asr_fallback:
                    manifest["notes"].append("Transcript missing. Re-run with --asr-fallback for full transcription.")

        else:
            manifest["platform"] = "search"
            search_url = f"https://s.jina.ai/{quote(source)}"
            try:
                search_text = http_get_text(search_url, args.timeout)
                manifest["files"]["search_via"] = search_url
            except Exception:
                search_text, fallback_url = fetch_duckduckgo_html(source, args.timeout)
                manifest["files"]["search_via"] = fallback_url
                manifest["notes"].append("s.jina.ai search unavailable; used DuckDuckGo HTML fallback.")

            search_path = outdir / "source_search.md"
            search_path.write_text(search_text, encoding="utf-8")
            manifest["files"]["source_search"] = str(search_path)
            manifest["candidates"] = extract_candidate_urls(search_text, limit=5)
            manifest["notes"].append("Input is a topic name. Please pick or confirm a canonical source link before deep analysis.")

    except Exception as exc:  # noqa: BLE001
        manifest["notes"].append(f"Fetch error: {exc}")

    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nManifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
