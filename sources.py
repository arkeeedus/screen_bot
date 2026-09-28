"""
sources.py — resolve a sources.json config (direct video links and/or channel
URLs to monitor) into a queue of new video URLs that haven't been processed
yet. Already-processed video IDs are tracked in <workdir>/seen.json so the
same video is never fetched twice.
"""

import json
import os
import re
import subprocess
import sys
from typing import Dict, List

VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})")


def load_config(path: str) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _seen_path(workdir: str) -> str:
    return os.path.join(workdir, "seen.json")


def load_seen(workdir: str) -> set:
    path = _seen_path(workdir)
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def mark_seen(workdir: str, video_id: str) -> None:
    if not video_id:
        return
    os.makedirs(workdir, exist_ok=True)
    seen = load_seen(workdir)
    seen.add(video_id)
    with open(_seen_path(workdir), "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


def extract_video_id(url: str) -> str:
    m = VIDEO_ID_RE.search(url)
    return m.group(1) if m else url


def list_channel_videos(channel_url: str, limit: int) -> List[Dict]:
    """Uses yt-dlp's flat-playlist mode to list a channel's recent uploads
    without downloading anything."""
    cmd = [
        sys.executable, "-m", "yt_dlp", "--flat-playlist", "--dump-json",
        "--playlist-end", str(limit), channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    videos = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            videos.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return videos


def resolve_new_sources(config: Dict, workdir: str) -> List[Dict]:
    seen = load_seen(workdir)
    queue: List[Dict] = []

    for url in config.get("direct", []):
        vid = extract_video_id(url)
        if vid not in seen:
            queue.append({"url": url, "id": vid, "title": None})

    limit = config.get("max_per_channel_check", 5)
    for channel_url in config.get("channels", []):
        for v in list_channel_videos(channel_url, limit):
            vid = v.get("id")
            url = v.get("webpage_url") or v.get("url")
            if vid and vid not in seen and url:
                queue.append({"url": url, "id": vid, "title": v.get("title")})

    return queue
