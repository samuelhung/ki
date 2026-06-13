"""Douyin share link parsing and video download."""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests  # type: ignore

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def extract_first_url(text: str) -> str:
    """Extract the first douyin short link from share text."""
    match = re.search(r"https?://v\.douyin\.com/\S+", text)
    if not match:
        return ""
    return match.group(0).rstrip("/)")


def parse_share_text(share_text: str) -> dict:
    """Parse a douyin share text and return video metadata.

    Returns dict with keys: video_id, platform_title, download_url, share_url
    """
    share_url = extract_first_url(share_text)
    if not share_url:
        raise ValueError("未找到抖音分享链接")

    headers = {"User-Agent": MOBILE_UA}
    session = requests.Session()

    # Step 1: follow short link redirect to get video_id
    r = session.get(share_url, headers=headers, allow_redirects=True, timeout=30)
    r.raise_for_status()
    video_id = r.url.split("?")[0].rstrip("/").split("/")[-1]

    # Step 2: fetch iesdouyin page with _ROUTER_DATA
    page_url = f"https://www.iesdouyin.com/share/video/{video_id}"
    page = session.get(page_url, headers=headers, timeout=30)
    page.raise_for_status()

    # Step 3: extract JSON from window._ROUTER_DATA
    marker = "window._ROUTER_DATA ="
    idx = page.text.find(marker)
    if idx < 0:
        raise RuntimeError("页面中未找到 window._ROUTER_DATA（抖音页面结构可能已变化）")

    start = page.text.find("{", idx)
    if start < 0:
        raise RuntimeError("window._ROUTER_DATA 后未找到 JSON 起始 {")

    depth = 0
    end = -1
    for i in range(start, len(page.text)):
        ch = page.text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        raise RuntimeError("未能从页面中截取完整的 window._ROUTER_DATA JSON")

    data = json.loads(page.text[start:end])
    loader = data.get("loaderData") or {}
    info_res = None
    for k in ("video_(id)/page", "note_(id)/page"):
        if k in loader and isinstance(loader[k], dict) and "videoInfoRes" in loader[k]:
            info_res = loader[k]["videoInfoRes"]
            break

    if not info_res:
        raise RuntimeError("未在 loaderData 中找到 videoInfoRes")

    item_list = info_res.get("item_list") or []
    if not item_list:
        raise RuntimeError("videoInfoRes.item_list 为空")

    item0 = item_list[0]
    desc = (item0.get("desc") or "").strip() or f"douyin_{video_id}"
    url_list = ((item0.get("video") or {}).get("play_addr") or {}).get("url_list") or []

    if not url_list:
        raise RuntimeError("未解析到 video.play_addr.url_list")

    play_url = str(url_list[0]).replace("playwm", "play")

    return {
        "video_id": video_id,
        "platform_title": desc,
        "download_url": play_url,
        "share_url": share_url,
        "_session": session,
    }


def download_video(url: str, dest: Path, session: requests.Session | None = None) -> Path:
    """Download a video from url and save to dest path.

    Uses HTTP Range requests to download in 1 MB segments,
    retrying each segment up to 3 times to survive CDN disconnects.
    If session is provided, reuses its cookies (from parse_share_text).
    Returns dest path on success.
    """
    import time as _time

    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }

    s = session or requests.Session()

    # Probe total size via HEAD (抖音 CDN usually honours Content-Length)
    total_size = 0
    try:
        _head = s.head(url, headers=headers, timeout=30)
        total_size = int(_head.headers.get("Content-Length", 0))
    except Exception:
        pass

    dest.parent.mkdir(parents=True, exist_ok=True)

    SEGMENT = 1 * 1024 * 1024  # 1 MB per segment
    downloaded = 0

    with open(dest, "wb") as f:
        while True:
            if total_size > 0 and downloaded >= total_size:
                break

            range_start = downloaded
            range_end = (downloaded + SEGMENT - 1) if total_size == 0 else min(downloaded + SEGMENT, total_size - 1)
            seg_headers = {**headers, "Range": f"bytes={range_start}-{range_end}"}

            # Retry up to 3 times per segment
            seg_ok = False
            for attempt in range(3):
                try:
                    seg = s.get(url, headers=seg_headers, stream=True, timeout=(30, 120))
                    if seg.status_code not in (200, 206):
                        seg.raise_for_status()
                    seg_len = 0
                    for chunk in seg.iter_content(chunk_size=65536):
                        f.write(chunk)
                        seg_len += len(chunk)
                    downloaded += seg_len
                    seg_ok = True
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    _time.sleep(1.5 * (attempt + 1))

            if not seg_ok:
                raise RuntimeError("Segment download failed after 3 retries")

            # When no total_size hint, stop after empty segment
            if total_size == 0 and seg_len < SEGMENT * 0.9:
                break

    return dest
