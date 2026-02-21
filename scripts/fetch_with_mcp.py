#!/usr/bin/env python3
"""
Fetch Douyin content using MCP + Local GPU ASR.

Flow:
1. Use MCP to get video download link (requires API key for MCP)
2. Download video with yt-dlp
3. Extract audio
4. Transcribe with LOCAL GPU ASR (faster-whisper) - NO API calls!

Usage:
    python scripts/fetch_with_mcp.py --input "https://v.douyin.com/xxxxx" --outdir ./output
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

# Import MCP functions for getting download links
from douyin_mcp_server.server import parse_douyin_link, extract_douyin_text


def load_config(config_path: str) -> dict:
    """Load MCP config file."""
    path = Path(config_path).expanduser()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def download_audio_with_ytdlp(video_url: str, outdir: Path) -> dict:
    """Download and extract audio using yt-dlp."""
    result = {
        "success": False,
        "audio_path": None,
        "error": None,
    }

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        result["error"] = "yt-dlp not found in PATH"
        return result

    # Download and extract audio in one step
    audio_pattern = str(outdir / "audio.%(ext)s")
    cmd = [
        yt_dlp,
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",  # Best quality
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
        print(f"✓ Audio downloaded: {audio_files[0].name} ({os.path.getsize(audio_files[0]) / 1024 / 1024:.1f} MB)")
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
        # Try alternative location
        transcribe_script = shutil.which("transcribe")
        if not transcribe_script:
            result["error"] = "faster-whisper transcribe script not found"
            return result

    # Build command for local ASR
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
    print(f"   Device: {config.get('local_asr_device', 'cuda')}")
    print(f"   Language: {language}")
    print(f"   This may take 5-10 minutes for a 1h37m video (GPU accelerated)")
    
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
        # Try to find any .txt file in output dir
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


def fetch_douyin(share_link: str, config: dict, outdir: Path) -> dict:
    """Fetch Douyin video and transcribe with LOCAL ASR."""
    result = {
        "platform": "douyin",
        "share_link": share_link,
        "video_info": None,
        "download_url": None,
        "audio_path": None,
        "transcript": None,
        "transcript_path": None,
        "errors": [],
    }

    # Step 1: Parse video info and get download link using MCP
    print("🔍 Parsing video info and getting download link...")
    try:
        # Use MCP parse_douyin_link function
        from douyin_mcp_server.server import parse_douyin_link
        
        result_str = parse_douyin_link(share_link)
        mcp_result = json.loads(result_str) if isinstance(result_str, str) else result_str
        result["mcp_raw"] = mcp_result
        
        if isinstance(mcp_result, dict):
            if mcp_result.get("status") == "success":
                # Extract video info
                result["video_info"] = {
                    "title": mcp_result.get("title"),
                    "author": mcp_result.get("author"),
                    "video_id": mcp_result.get("video_id"),
                }
                print(f"✓ Video: {mcp_result.get('title', 'Unknown')}")
                
                # Get download URL - check multiple field names
                download_url = (
                    mcp_result.get("download_url") or 
                    mcp_result.get("video_url") or 
                    mcp_result.get("url") or 
                    mcp_result.get("play_url")
                )
                if download_url:
                    result["download_url"] = download_url
                    print(f"✓ Download link obtained: {download_url[:80]}...")
                else:
                    result["errors"].append("No download URL in MCP response")
                    print(f"⚠️  No download URL in MCP response")
                    print(f"   Available fields: {list(mcp_result.keys())}")
            else:
                error_msg = mcp_result.get("error", "Unknown error")
                result["errors"].append(f"MCP failed: {error_msg}")
                print(f"⚠️  MCP failed: {error_msg}")
    except Exception as exc:
        result["errors"].append(f"MCP parsing failed: {exc}")
        import traceback
        traceback.print_exc()

    # Step 3: Download audio
    print("\n📥 Downloading audio...")
    if result["download_url"]:
        dl_result = download_audio_with_ytdlp(result["download_url"], outdir)
        if dl_result["success"]:
            result["audio_path"] = dl_result["audio_path"]
        else:
            result["errors"].append(f"Download failed: {dl_result['error']}")
            return result

    # Step 4: LOCAL ASR Transcription (NO API CALLS!)
    print("\n🎤 Starting LOCAL ASR transcription...")
    if result["audio_path"]:
        asr_result = transcribe_with_local_asr(result["audio_path"], config, outdir)
        if asr_result["success"]:
            result["transcript"] = asr_result["transcript"]
            result["transcript_path"] = asr_result["transcript_path"]
        else:
            result["errors"].append(f"ASR failed: {asr_result['error']}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Douyin content + LOCAL GPU ASR.")
    parser.add_argument("--input", required=True, help="Douyin share link")
    parser.add_argument("--outdir", default="./omni_learning_output", help="Output directory")
    parser.add_argument("--config", default="~/.openclaw/skills/omni-link-learning/config.json", 
                        help="Config file path")
    parser.add_argument("--skip-asr", action="store_true", help="Skip ASR transcription")
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)
    
    # Set API key as environment variable for MCP
    if config.get("api_key"):
        os.environ["DASHSCOPE_API_KEY"] = config["api_key"]
        print(f"✓ API key loaded from config")
    
    # Detect platform
    input_url = args.input.strip()
    is_douyin = "douyin.com" in input_url or "v.douyin.com" in input_url
    is_xiaohongshu = "xiaohongshu.com" in input_url or "xhslink.com" in input_url or "xhs.com" in input_url

    if not (is_douyin or is_xiaohongshu):
        print("❌ Error: URL must be from Douyin or Xiaohongshu")
        print(f"   Detected: {input_url[:50]}...")
        return 1

    platform_name = "Douyin" if is_douyin else "Xiaohongshu"
    print(f"🎯 Platform: {platform_name}")
    print(f"📥 Input: {input_url}")
    print(f"📂 Output: {outdir}")
    print(f"🎤 ASR: LOCAL GPU (faster-whisper)")
    print(f"⚡ Device: {config.get('local_asr_device', 'cuda')}")
    print(f"🧠 Model: {config.get('local_asr_model', 'large-v3-turbo')}\n")

    # Fetch and transcribe
    result = fetch_douyin(input_url, config, outdir)

    # Save results
    result_path = outdir / "douyin_mcp_result.json"
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
    
    if result.get("video_info"):
        vi = result["video_info"]
        if isinstance(vi, dict):
            if vi.get("title"):
                print(f"✓ Title: {vi['title']}")
            if vi.get("author"):
                print(f"✓ Author: {vi.get('author')}")
    
    if result.get("audio_path"):
        audio_size = os.path.getsize(result["audio_path"]) / 1024 / 1024
        print(f"✓ Audio: {Path(result['audio_path']).name} ({audio_size:.1f} MB)")
    
    if result.get("transcript"):
        print(f"✓ Transcript: {len(result['transcript'])} characters")
        print(f"   File: {result['transcript_path']}")

    # Next steps
    if result.get("transcript"):
        print("\n🎉 Complete! Next you can:")
        print("   1. Run plan_study.py to generate study plan")
        print("   2. Run deep analysis")
        print("   3. Generate action items")

    return 0


if __name__ == "__main__":
    sys.exit(main())
