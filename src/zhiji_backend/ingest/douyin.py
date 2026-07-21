"""Douyin share link parsing and video download."""

from __future__ import annotations

import json
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

import requests  # type: ignore
from requests.cookies import get_cookie_header
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util import Timeout

from ..security.file_intake import REMOTE_VIDEO_MAX_BYTES

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
MAX_VIDEO_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class _RemoteTarget:
    scheme: str
    hostname: str
    port: int
    host_header: str
    request_target: str
    public_ips: tuple[str, ...]


class _PinnedResponse:
    def __init__(self, response, pool) -> None:
        self._response = response
        self._pool = pool
        self.status_code = response.status
        self.headers = response.headers
        self._closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        try:
            yield from self._response.stream(chunk_size, decode_content=False)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._response.close()
        self._pool.close()


class _PinnedConnection:
    def __init__(self, pool) -> None:
        self._pool = pool

    def get(self, target: str, *, headers: dict, timeout):
        if isinstance(timeout, tuple):
            timeout = Timeout(connect=timeout[0], read=timeout[1])
        try:
            response = self._pool.urlopen(
                "GET",
                target,
                headers=headers,
                timeout=timeout,
                redirect=False,
                retries=False,
                preload_content=False,
                decode_content=False,
            )
        except BaseException:
            self._pool.close()
            raise
        return _PinnedResponse(response, self._pool)


def create_pinned_connection(scheme: str, ip: str, port: int, hostname: str):
    if scheme == "https":
        pool = HTTPSConnectionPool(
            ip,
            port=port,
            assert_hostname=hostname,
            server_hostname=hostname,
            cert_reqs=ssl.CERT_REQUIRED,
            maxsize=1,
            block=True,
        )
    else:
        pool = HTTPConnectionPool(ip, port=port, maxsize=1, block=True)
    return _PinnedConnection(pool)


def is_trusted_365yg_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").rstrip(".").lower()
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and (host == "365yg.com" or host.endswith(".365yg.com"))
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
        if is_trusted_365yg_url(u_str):
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


def _declared_size(response) -> int | None:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Length") if hasattr(headers, "get") else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_host(host: str, port: int) -> list[str]:
    addresses = {
        sockaddr[0]
        for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    }
    return sorted(addresses)


def _validate_remote_url(
    url: str,
    *,
    resolver: Callable[[str, int], list[str]],
) -> _RemoteTarget:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("远程视频端口无效") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("不支持的远程视频协议")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("远程视频地址不得包含凭据")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise ValueError("远程视频地址缺少主机名")
    scheme = parsed.scheme.lower()
    effective_port = port or (443 if scheme == "https" else 80)
    resolved = resolver(host, effective_port)
    if not resolved:
        raise ValueError("远程视频主机无法解析")
    try:
        addresses = [ipaddress.ip_address(value) for value in resolved]
    except ValueError as exc:
        raise ValueError("远程视频主机解析结果无效") from exc
    public_ips = tuple(sorted({str(address) for address in addresses if address.is_global}))
    if not public_ips:
        raise ValueError("远程视频地址必须解析到公网 IP")
    host_header = f"[{host}]" if ":" in host else host
    if port is not None:
        host_header = f"{host_header}:{port}"
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return _RemoteTarget(
        scheme=scheme,
        hostname=host,
        port=effective_port,
        host_header=host_header,
        request_target=request_target,
        public_ips=public_ips,
    )


def _session_cookie_header(session: requests.Session | None, url: str) -> str | None:
    if session is None:
        return None
    prepared = requests.Request("GET", url).prepare()
    return get_cookie_header(session.cookies, prepared)


def _safe_get(
    session: requests.Session | None,
    url: str,
    *,
    headers: dict,
    timeout,
    resolver: Callable[[str, int], list[str]],
    max_redirects: int,
    connection_factory,
):
    current = url
    visited: set[str] = set()
    redirects = 0
    while True:
        if current in visited:
            raise ValueError("远程视频重定向循环")
        visited.add(current)
        target = _validate_remote_url(current, resolver=resolver)
        request_headers = {**headers, "Host": target.host_header}
        cookie_header = _session_cookie_header(session, current)
        if cookie_header:
            request_headers["Cookie"] = cookie_header
        connection = connection_factory(
            target.scheme,
            target.public_ips[0],
            target.port,
            target.hostname,
        )
        response = connection.get(
            target.request_target,
            headers=request_headers,
            timeout=timeout,
        )
        if response.status_code not in _REDIRECT_STATUSES:
            return response
        if redirects >= max_redirects:
            response.close()
            raise ValueError("远程视频重定向次数超过限制")
        location = response.headers.get("Location") if hasattr(response.headers, "get") else None
        if not location:
            response.close()
            raise ValueError("远程视频重定向缺少 Location")
        close = getattr(response, "close", None)
        if callable(close):
            close()
        current = urljoin(current, location)
        redirects += 1


def _download_whole(
    url: str,
    dest: Path,
    headers: dict,
    s: requests.Session | None,
    *,
    max_bytes: int,
    resolver: Callable[[str, int], list[str]],
    max_redirects: int,
    connection_factory,
) -> bool:
    """Fallback: download the whole file in a single GET without Range headers.
    Returns True on success, False on failure.
    """
    resp = None
    try:
        resp = _safe_get(
            s,
            url,
            headers=headers,
            timeout=(30, 600),
            resolver=resolver,
            max_redirects=max_redirects,
            connection_factory=connection_factory,
        )
        resp.raise_for_status()
        declared = _declared_size(resp)
        if declared is not None and declared > max_bytes:
            raise ValueError("远程视频大小超过限制")
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError("远程视频大小超过限制")
                f.write(chunk)
        return True
    except ValueError:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        return False
    finally:
        if resp is not None:
            resp.close()


def download_video(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    *,
    max_bytes: int = REMOTE_VIDEO_MAX_BYTES,
    resolver: Callable[[str, int], list[str]] = _resolve_host,
    max_redirects: int = MAX_VIDEO_REDIRECTS,
    connection_factory=create_pinned_connection,
) -> Path:
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

    s = session

    # Probe total size via HEAD (抖音 365yg CDN usually honours Content-Length)
    # Skip HEAD if it might consume a one-time signed URL — go segmented first,
    # fall back to whole-file if Range is rejected.
    total_size = 0
    range_supported = True

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        # If total_size is unknown or server rejects Range, skip straight to whole-file
        if total_size == 0 or not range_supported:
            if _download_whole(
                url,
                dest,
                headers,
                s,
                max_bytes=max_bytes,
                resolver=resolver,
                max_redirects=max_redirects,
                connection_factory=connection_factory,
            ):
                return dest
            # Fall through to segmented — maybe the direct request was transient.
            total_size = 0

        segment_size = 1 * 1024 * 1024
        downloaded = 0
        range_rejected = False

        with open(dest, "wb") as f:
            while True:
                if total_size > 0 and downloaded >= total_size:
                    break

                range_start = downloaded
                range_end = (
                    downloaded + segment_size - 1
                    if total_size == 0
                    else min(downloaded + segment_size, total_size - 1)
                )
                seg_headers = {**headers, "Range": f"bytes={range_start}-{range_end}"}
                seg = _safe_get(
                    s,
                    url,
                    headers=seg_headers,
                    timeout=(30, 120),
                    resolver=resolver,
                    max_redirects=max_redirects,
                    connection_factory=connection_factory,
                )
                try:
                    if seg.status_code not in (200, 206):
                        range_rejected = True
                    else:
                        declared = _declared_size(seg)
                        if declared is not None and declared > max_bytes:
                            raise ValueError("远程视频大小超过限制")
                        seg_len = 0
                        for chunk in seg.iter_content(chunk_size=65536):
                            if not chunk:
                                continue
                            seg_len += len(chunk)
                            downloaded += len(chunk)
                            if downloaded > max_bytes:
                                raise ValueError("远程视频大小超过限制")
                            f.write(chunk)
                finally:
                    seg.close()

                if range_rejected:
                    f.close()
                    if _download_whole(
                        url,
                        dest,
                        headers,
                        s,
                        max_bytes=max_bytes,
                        resolver=resolver,
                        max_redirects=max_redirects,
                        connection_factory=connection_factory,
                    ):
                        return dest
                    raise RuntimeError("Whole-file fallback download failed")

                if seg.status_code == 200:
                    break
                if total_size == 0 and seg_len < segment_size * 0.9:
                    break

        return dest
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
