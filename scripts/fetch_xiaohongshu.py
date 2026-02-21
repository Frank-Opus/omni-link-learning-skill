#!/usr/bin/env python3
"""
Fetch Xiaohongshu content without API key.

Uses:
- Direct HTTP requests to parse share links
- yt-dlp for downloading videos
- Local GPU ASR for transcription

Usage:
    python scripts/fetch_xiaohongshu.py --input "http://xhslink.com/xxx" --outdir ./output
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import shutil
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.xiaohongshu.com/",
}


def parse_xiaohongshu_share_link(share_link: str) -> dict:
    """Parse Xiaohongshu share link to get note ID and redirect URL."""
    result = {
        "success": False,
        "note_id": None,
        "redirect_url": None,
        "error": None,
    }

    try:
        # Follow redirect
        response = requests.get(share_link, headers=HEADERS, allow_redirects=True)
        final_url = response.url
        
        # Extract note ID (support both /explore/ and /discovery/item/)
        note_id_match = re.search(r'(?:/explore/|/discovery/item/)([a-zA-Z0-9]+)', final_url)
        if note_id_match:
            result["note_id"] = note_id_match.group(1)
            result["redirect_url"] = final_url
            result["success"] = True
            print(f"✓ Note ID: {result['note_id']}")
        else:
            # Try to find note ID in query parameters
            note_id_param = re.search(r'[?&]note_id=([a-zA-Z0-9]+)', final_url)
            if note_id_param:
                result["note_id"] = note_id_param.group(1)
                result["redirect_url"] = final_url
                result["success"] = True
                print(f"✓ Note ID (from param): {result['note_id']}")
            else:
                result["error"] = f"Could not extract note ID from: {final_url}"
    except Exception as exc:
        result["error"] = f"Parse failed: {exc}"

    return result


def fetch_xiaohongshu_note(note_id: str) -> dict:
    """Fetch note info from Xiaohongshu."""
    result = {
        "title": None,
        "desc": None,
        "author": None,
        "images": [],
        "video_url": None,
        "type": None,  # "image" or "video"
        "error": None,
    }

    try:
        # Use Xiaohongshu web API
        api_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        headers = {
            **HEADERS,
            "Cookie": "web_session=verify_test",
        }
        
        response = requests.get(api_url, headers=headers)
        html = response.text
        
        # Extract title
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            result["title"] = title_match.group(1).replace(" - 小红书", "").strip()
        
        # Extract description (look for JSON-LD or meta tags)
        desc_match = re.search(r'"description":"([^"]+)"', html)
        if desc_match:
            result["desc"] = desc_match.group(1).replace("\\n", "\n")
        
        # Extract author
        author_match = re.search(r'"authorName":"([^"]+)"', html)
        if author_match:
            result["author"] = author_match.group(1)
        
        # Extract images
        image_matches = re.findall(r'"imageUrl":"([^"]+)"', html)
        if image_matches:
            result["images"] = image_matches[:5]  # First 5 images
        
        # Extract video URL if present
        video_match = re.search(r'"videoUrl":"([^"]+)"', html)
        if video_match:
            result["video_url"] = video_match.group(1)
            result["type"] = "video"
        elif result["images"]:
            result["type"] = "image"
        
        if result["title"]:
            print(f"✓ Title: {result['title']}")
        if result["author"]:
            print(f"✓ Author: {result['author']}")
        if result["type"]:
            print(f"✓ Type: {result['type']}")
            if result["type"] == "image":
                print(f"✓ Images: {len(result['images'])}")
            else:
                print(f"✓ Has video")
                
    except Exception as exc:
        result["error"] = f"Fetch failed: {exc}"

    return result


def download_audio_from_xiaohongshu(video_url: str, outdir: Path) -> dict:
    """Download and extract audio from Xiaohongshu video."""
    result = {
        "success": False,
        "audio_path": None,
        "error": None,
    }

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        result["error"] = "yt-dlp not found in PATH"
        return result

    # Download and extract audio
    audio_pattern = str(outdir / "audio.%(ext)s")
    cmd = [
        yt_dlp,
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-playlist",
        "-o", audio_pattern,
        video_url,
    ]

    print(f"📥 Downloading and extracting audio...")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if proc.returncode != 0:
        result["error"] = f"Download failed: {proc.stderr[-500:]}"
        return result

    # Find downloaded file
    audio_files = list(outdir.glob("audio.*"))
    if audio_files:
        result["audio_path"] = str(audio_files[0])
        result["success"] = True
        print(f"✓ Audio downloaded: {audio_files[0].name} ({len(audio_files[0]) / 1024 / 1024:.1f} MB)")
    else:
        result["error"] = "Download completed but file not found"

    return result


def transcribe_with_local_asr(audio_path: str, config: dict, outdir: Path) -> dict:
    """Transcribe audio using LOCAL faster-whisper (GPU accelerated)."""
    result = {
        "success": False,
        "transcript_path": None,
        "transcript": None,
        "error": None,
    }

    # Find faster-whisper transcribe script
    transcribe_script = Path.home() / ".codex" / "skills" / "faster-whisper" / "scripts" / "transcribe"
    
    if not transcribe_script.exists():
        transcribe_script = shutil.which("transcribe")
        if not transcribe_script:
            result["error"] = "faster-whisper transcribe script not found"
            return result

    model = config.get("local_asr_model", "large-v3-turbo")
    language = config.get("local_asr_language", "zh")
    
    output_txt = outdir / "transcript.txt"
    
    cmd = [
        str(transcribe_script),
        "--model", model,
        "--language", language,
        "--output", str(output_txt),
        audio_path,
    ]

    print(f"\n🎤 Starting LOCAL GPU ASR transcription...")
    print(f"   Model: {model}")
    print(f"   Language: {language}")
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if proc.returncode != 0:
        result["error"] = f"ASR failed: {proc.stderr[-500:]}"
        return result

    # Find transcript
    if output_txt.exists():
        result["transcript_path"] = str(output_txt)
        with open(output_txt, "r", encoding="utf-8") as f:
            result["transcript"] = f.read()
        result["success"] = True
        print(f"✓ Transcription completed: {len(result['transcript'])} characters")
    else:
        txt_files = list(outdir.glob("*.txt"))
        if txt_files:
            result["transcript_path"] = str(txt_files[0])
            with open(txt_files[0], "r", encoding="utf-8") as f:
                result["transcript"] = f.read()
            result["success"] = True
            print(f"✓ Transcription completed: {len(result['transcript'])} characters")
        else:
            result["error"] = "Transcription completed but output file not found"

    return result


def fetch_xiaohongshu(share_link: str, config: dict, outdir: Path) -> dict:
    """Fetch Xiaohongshu note and transcribe if video."""
    result = {
        "platform": "xiaohongshu",
        "share_link": share_link,
        "note_info": None,
        "video_url": None,
        "audio_path": None,
        "transcript": None,
        "transcript_path": None,
        "errors": [],
    }

    # Step 1: Parse share link
    print("🔍 Parsing share link...")
    parse_result = parse_xiaohongshu_share_link(share_link)
    if not parse_result["success"]:
        result["errors"].append(f"Parse failed: {parse_result['error']}")
        return result

    note_id = parse_result["note_id"]

    # Step 2: Fetch note info
    print("\n📊 Fetching note info...")
    note_info = fetch_xiaohongshu_note(note_id)
    result["note_info"] = note_info
    
    if note_info["error"]:
        result["errors"].append(f"Note info: {note_info['error']}")

    # Step 3: Download audio if video
    if note_info.get("video_url"):
        print("\n📥 Downloading video audio...")
        result["video_url"] = note_info["video_url"]
        dl_result = download_audio_from_xiaohongshu(note_info["video_url"], outdir)
        if dl_result["success"]:
            result["audio_path"] = dl_result["audio_path"]
        else:
            result["errors"].append(f"Download failed: {dl_result['error']}")

    # Step 4: LOCAL ASR Transcription (if audio available)
    if result.get("audio_path"):
        print("\n🎤 Starting LOCAL ASR transcription...")
        asr_result = transcribe_with_local_asr(result["audio_path"], config, outdir)
        if asr_result["success"]:
            result["transcript"] = asr_result["transcript"]
            result["transcript_path"] = asr_result["transcript_path"]
        else:
            result["errors"].append(f"ASR failed: {asr_result['error']}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Xiaohongshu content + LOCAL GPU ASR.")
    parser.add_argument("--input", required=True, help="Xiaohongshu share link")
    parser.add_argument("--outdir", default="./omni_learning_output", help="Output directory")
    parser.add_argument("--config", default="~/.openclaw/skills/omni-link-learning/config.json", 
                        help="Config file path")
    parser.add_argument("--skip-asr", action="store_true", help="Skip ASR transcription")
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    config = {}
    config_path = Path(args.config).expanduser()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # Detect platform
    input_url = args.input.strip()
    is_xiaohongshu = "xiaohongshu.com" in input_url or "xhslink.com" in input_url or "xhs.com" in input_url

    if not is_xiaohongshu:
        print("❌ Error: URL must be from Xiaohongshu")
        return 1

    print(f"🎯 Platform: Xiaohongshu")
    print(f"📥 Input: {input_url}")
    print(f"📂 Output: {outdir}")
    print(f"🎤 ASR: LOCAL GPU (faster-whisper)")
    print(f"🧠 Model: {config.get('local_asr_model', 'large-v3-turbo')}\n")

    # Fetch and transcribe
    result = fetch_xiaohongshu(input_url, config, outdir)

    # Save results
    result_path = outdir / "xiaohongshu_mcp_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results saved to: {result_path}")

    # Print summary
    print("\n📊 Summary:")
    if result.get("errors"):
        print(f"⚠️  Errors: {len(result['errors'])}")
        for err in result["errors"]:
            print(f"   - {err}")
    else:
        print("✓ No errors!")
    
    if result.get("note_info"):
        ni = result["note_info"]
        if ni.get("title"):
            print(f"✓ Title: {ni['title']}")
        if ni.get("author"):
            print(f"✓ Author: {ni['author']}")
        if ni.get("type"):
            print(f"✓ Type: {ni['type']}")
    
    if result.get("audio_path"):
        audio_size = Path(result["audio_path"]).stat().st_size / 1024 / 1024
        print(f"✓ Audio: {Path(result['audio_path']).name} ({audio_size:.1f} MB)")
    
    if result.get("transcript"):
        print(f"✓ Transcript: {len(result['transcript'])} characters")
        print(f"   File: {result['transcript_path']}")

    # Next steps
    if result.get("transcript"):
        print("\n🎉 Complete! Next you can:")
        print("   python3 scripts/deep_reader.py --input transcript.txt --output deep_reading.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
