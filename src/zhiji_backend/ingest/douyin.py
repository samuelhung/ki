"""Douyin share link parsing and video download."""

from __future__ import annotations

import json
import re
from html import unescape
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


def _decode_json_object_after(text: str, marker: str) -> dict | None:
    """Decode a JSON object that appears immediately after a marker."""
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    colon_index = text.find(":", marker_index + len(marker))
    if colon_index < 0:
        return None
    object_start = text.find("{", colon_index)
    if object_start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[object_start:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _aweme_from_page_html(page_html: str) -> dict:
    """Extract aweme metadata from Douyin's share landing page HTML."""
    text = unescape(page_html or "")

    video_info = _decode_json_object_after(text, '"videoInfoRes"')
    if video_info:
        item_list = video_info.get("item_list") or []
        if item_list:
            return item_list[0] or {}

    router_data = _decode_json_object_after(text, "window._ROUTER_DATA")
    if router_data:
        video_info = (
            router_data.get("loaderData", {})
            .get("video_(id)/page", {})
            .get("videoInfoRes", {})
        )
        item_list = video_info.get("item_list") or []
        if item_list:
            return item_list[0] or {}

    return {}


def parse_share_text(share_text: str) -> dict:
    """Parse a douyin share text and return video metadata.

    Uses the official douyin.com web API to get fresh CDN URLs
    (avoids iesdouyin.com URLs with short-lived l= signatures).

    Returns dict with keys: video_id, platform_title, download_url, share_url
    """
    share_url = extract_first_url(share_text)
    if not share_url:
        raise ValueError("未找到抖音分享链接")

    headers = {"User-Agent": MOBILE_UA}
    session = requests.Session()

    # Step 1: follow short link redirect to get numeric aweme_id
    r = session.get(share_url, headers=headers, allow_redirects=True, timeout=30)
    r.raise_for_status()
    aweme_id = r.url.split("?")[0].rstrip("/").split("/")[-1]

    # Step 2: hit the official douyin web API for video detail
    api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}"
    detail_resp = session.get(
        api_url,
        headers={**headers, "Referer": "https://www.douyin.com/"},
        timeout=30,
    )
    detail_resp.raise_for_status()

    data = {}
    if (detail_resp.text or "").strip():
        try:
            data = detail_resp.json()
        except ValueError:
            data = {}
    aweme = data.get("aweme_detail") or {}
    if not aweme:
        aweme = _aweme_from_page_html(r.text)
    if not aweme:
        raise RuntimeError(
            "抖音详情接口未返回可解析数据，且落地页未找到 videoInfoRes"
            f"（status={detail_resp.status_code}, "
            f"content_type={detail_resp.headers.get('content-type', '')}, "
            f"body_len={len(detail_resp.text or '')}）"
        )

    desc = (aweme.get("desc") or "").strip() or f"douyin_{aweme_id}"
    video_info = aweme.get("video") or {}
    play_addr = video_info.get("play_addr") or {}
    url_list = play_addr.get("url_list") or []

    if not url_list:
        raise RuntimeError("未解析到 video.play_addr.url_list")

    # Prefer 365yg CDN URLs (no short-lived signature); use api-play as fallback
    play_url = ""
    for u in url_list:
        u_str = str(u)
        if "365yg.com" in u_str:
            play_url = u_str
            break
    if not play_url:
        play_url = str(url_list[-1])  # fallback: last URL (api-play redirect)

    # Replace playwm with play for direct download
    play_url = play_url.replace("playwm", "play")

    return {
        "video_id": aweme_id,
        "platform_title": desc,
        "download_url": play_url,
        "share_url": share_url,
        "_session": session,
    }


def _download_whole(url: str, dest: Path, headers: dict, s: requests.Session) -> bool:
    """Fallback: download the whole file in a single GET without Range headers.
    Returns True on success, False on failure.
    """
    try:
        resp = s.get(url, headers=headers, stream=True, timeout=(30, 600))
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception:
        return False


def download_video(url: str, dest: Path, session: requests.Session | None = None) -> Path:
    """Download a video from url and save to dest path.

    Uses HTTP Range requests to download in 1 MB segments,
    retrying each segment up to 3 times to survive CDN disconnects.
    Falls back to whole-file download if the CDN rejects Range (416).
    If session is provided, reuses its cookies (from parse_share_text).
    Returns dest path on success.
    """

    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }

    s = session or requests.Session()

    # Probe total size via HEAD (抖音 365yg CDN usually honours Content-Length)
    # Skip HEAD if it might consume a one-time signed URL — go segmented first,
    # fall back to whole-file if Range is rejected.
    total_size = 0
    range_supported = True

    dest.parent.mkdir(parents=True, exist_ok=True)

    # If total_size is unknown or server rejects Range, skip straight to whole-file
    if total_size == 0 or not range_supported:
        if _download_whole(url, dest, headers, s):
            return dest
        # Fall through to segmented — maybe HEAD lied
        total_size = 0

    SEGMENT = 1 * 1024 * 1024  # 1 MB per segment
    downloaded = 0
    range_rejected = False

    with open(dest, "wb") as f:
        while True:
            if total_size > 0 and downloaded >= total_size:
                break

            range_start = downloaded
            range_end = (downloaded + SEGMENT - 1) if total_size == 0 else min(downloaded + SEGMENT, total_size - 1)
            seg_headers = {**headers, "Range": f"bytes={range_start}-{range_end}"}

            # One-shot: if Range fails, fall back to whole-file immediately
            seg = s.get(url, headers=seg_headers, stream=True, timeout=(30, 120))
            if seg.status_code not in (200, 206):
                # CDN rejects Range → fall back to whole-file download
                range_rejected = True
            else:
                seg_len = 0
                for chunk in seg.iter_content(chunk_size=65536):
                    f.write(chunk)
                    seg_len += len(chunk)
                downloaded += seg_len

            if range_rejected:
                # Close current file handle and re-download whole
                f.close()
                if _download_whole(url, dest, headers, s):
                    return dest
                raise RuntimeError("Whole-file fallback download failed")

            # When no total_size hint, stop after empty segment
            if total_size == 0 and seg_len < SEGMENT * 0.9:
                break

    return dest
