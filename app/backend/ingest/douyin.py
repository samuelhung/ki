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

    # Step 1: follow short link redirect to get video_id
    r = requests.get(share_url, headers=headers, allow_redirects=True, timeout=30)
    r.raise_for_status()
    video_id = r.url.split("?")[0].rstrip("/").split("/")[-1]

    # Step 2: fetch iesdouyin page with _ROUTER_DATA
    page_url = f"https://www.iesdouyin.com/share/video/{video_id}"
    page = requests.get(page_url, headers=headers, timeout=30)
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
    }


def download_video(url: str, dest: Path) -> Path:
    """Download a video from url and save to dest path.

    Returns dest path on success.
    """
    headers = {"User-Agent": MOBILE_UA}
    r = requests.get(url, headers=headers, stream=True, timeout=120)
    r.raise_for_status()

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

    return dest
