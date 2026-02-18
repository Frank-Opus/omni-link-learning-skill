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
    "douyin": ("douyin.com", "iesdouyin.com", "v.douyin.com"),
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


def http_get_text(url: str, timeout: int, headers: dict[str, str] | None = None) -> str:
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
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


def normalize_source_url(source: str, platform: str) -> str:
    if platform != "bilibili":
        return source
    bvid = extract_bilibili_bvid(source)
    if not bvid:
        return source
    return f"https://www.bilibili.com/video/{bvid}"


def sec_to_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


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

    audio_pattern = outdir / "asr_audio.%(ext)s"
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
        source_url,
    ]
    dl = subprocess.run(dl_cmd, capture_output=True, text=True, check=False)
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

    if language.lower().startswith("zh") and cjk_ratio < 0.08:
        result["note"] = (
            f"ASR transcript quality looks low for zh (cjk_ratio={cjk_ratio}). "
            "Consider re-running with --asr-model large-v3-turbo."
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and normalize source content.")
    parser.add_argument("--input", required=True, help="URL or topic name")
    parser.add_argument("--outdir", default="./omni_learning_output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
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

            read_url = f"https://r.jina.ai/{normalized_source}"
            source_text = http_get_text(read_url, args.timeout)
            read_path = outdir / "source_read.md"
            read_path.write_text(source_text, encoding="utf-8")
            manifest["files"]["source_read"] = str(read_path)
            manifest["files"]["read_via"] = read_url

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

            if platform in {"bilibili", "douyin", "xiaoyuzhou"}:
                subtitle_result = try_extract_subtitles(normalized_source, outdir)
                manifest["files"]["subtitle_files"] = subtitle_result["subtitle_files"]
                manifest["files"]["transcript"] = subtitle_result["transcript_path"]
                if subtitle_result["note"]:
                    manifest["notes"].append(str(subtitle_result["note"]))

                if not subtitle_result["transcript_path"] and args.asr_fallback:
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
