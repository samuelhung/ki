"""Douyin parsing facade with backwards-compatible download exports."""

from __future__ import annotations

import inspect
import ipaddress
import json
import re
from collections.abc import Callable
from html import unescape
from pathlib import Path

import requests  # type: ignore
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool

from ..security.file_intake import REMOTE_VIDEO_MAX_BYTES
from . import douyin_download, remote_transport

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
MAX_VIDEO_REDIRECTS = 5
_PROXY_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")

_RemoteTarget = remote_transport._RemoteTarget
_PinnedConnection = remote_transport._PinnedConnection
_REDIRECT_STATUSES = remote_transport._REDIRECT_STATUSES

_CREATE_PINNED_CONNECTION_IMPLEMENTATION = remote_transport.create_pinned_connection
_SAFE_GET_IMPLEMENTATION = remote_transport._safe_get
_DOWNLOAD_WHOLE_IMPLEMENTATION = douyin_download._download_whole
_DOWNLOAD_VIDEO_IMPLEMENTATION = douyin_download.download_video


class _PinnedResponse(remote_transport._PinnedResponse):
    def __init__(self, response, pool) -> None:
        super().__init__(response, pool)
        self._requests_provider = lambda: requests


def create_pinned_connection(scheme: str, ip: str, port: int, hostname: str):
    implementation = remote_transport.create_pinned_connection
    if implementation is not _CREATE_PINNED_CONNECTION_IMPLEMENTATION:
        return implementation(scheme, ip, port, hostname)
    return implementation(
        scheme,
        ip,
        port,
        hostname,
        http_pool_cls=HTTPConnectionPool,
        https_pool_cls=HTTPSConnectionPool,
        connection_cls=_PinnedConnection,
        response_cls=_PinnedResponse,
    )


def is_trusted_365yg_url(url: str) -> bool:
    return remote_transport.is_trusted_365yg_url(url)


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
    """Parse Douyin share text and return video metadata."""
    share_url = extract_first_url(share_text)
    if not share_url:
        raise ValueError("未找到抖音分享链接")

    headers = {"User-Agent": MOBILE_UA}
    session = requests.Session()
    response = session.get(
        share_url,
        headers=headers,
        allow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    aweme_id = response.url.split("?")[0].rstrip("/").split("/")[-1]

    api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}"
    detail_response = session.get(
        api_url,
        headers={**headers, "Referer": "https://www.douyin.com/"},
        timeout=30,
    )
    detail_response.raise_for_status()

    data = {}
    if (detail_response.text or "").strip():
        try:
            data = detail_response.json()
        except ValueError:
            data = {}
    aweme = data.get("aweme_detail") or {}
    if not aweme:
        aweme = _aweme_from_page_html(response.text)
    if not aweme:
        raise RuntimeError(
            "抖音详情接口未返回可解析数据，且落地页未找到 videoInfoRes"
            f"（status={detail_response.status_code}, "
            f"content_type={detail_response.headers.get('content-type', '')}, "
            f"body_len={len(detail_response.text or '')}）"
        )

    description = (aweme.get("desc") or "").strip() or f"douyin_{aweme_id}"
    video_info = aweme.get("video") or {}
    play_address = video_info.get("play_addr") or {}
    url_list = play_address.get("url_list") or []
    if not url_list:
        raise RuntimeError("未解析到 video.play_addr.url_list")

    play_url = ""
    for candidate in url_list:
        candidate_url = str(candidate)
        if is_trusted_365yg_url(candidate_url):
            play_url = candidate_url
            break
    if not play_url:
        play_url = str(url_list[-1])

    return {
        "video_id": aweme_id,
        "platform_title": description,
        "download_url": play_url.replace("playwm", "play"),
        "share_url": share_url,
        "_session": session,
    }


def _declared_size(response) -> int | None:
    return douyin_download._declared_size(response)


def _resolve_host(host: str, port: int) -> list[str]:
    return remote_transport._resolve_host(host, port)


def _validate_remote_url(
    url: str,
    *,
    resolver: Callable[[str, int], list[str]],
) -> _RemoteTarget:
    return remote_transport._validate_remote_url(
        url,
        resolver=resolver,
        allow_non_global_address=_allow_trusted_douyin_fake_ip,
    )


def _allow_trusted_douyin_fake_ip(
    scheme: str,
    hostname: str,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    trusted_host = (
        hostname == "aweme.snssdk.com"
        or hostname == "365yg.com"
        or hostname.endswith(".365yg.com")
    )
    return (
        scheme == "https"
        and trusted_host
        and address.version == 4
        and address in _PROXY_FAKE_IP_NETWORK
    )


def _session_cookie_header(session: requests.Session | None, url: str) -> str | None:
    return remote_transport._session_cookie_header(
        session,
        url,
        requests_module=requests,
    )


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
    implementation = remote_transport._safe_get
    if implementation is not _SAFE_GET_IMPLEMENTATION:
        return implementation(
            session,
            url,
            headers=headers,
            timeout=timeout,
            resolver=resolver,
            max_redirects=max_redirects,
            connection_factory=connection_factory,
        )
    return implementation(
        session,
        url,
        headers=headers,
        timeout=timeout,
        resolver=resolver,
        max_redirects=max_redirects,
        connection_factory=connection_factory,
        requests_module=requests,
        validate_remote_url_fn=_validate_remote_url,
        cookie_header_fn=_session_cookie_header,
        redirect_statuses=_REDIRECT_STATUSES,
    )


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
    implementation = douyin_download._download_whole
    if implementation is not _DOWNLOAD_WHOLE_IMPLEMENTATION:
        return implementation(
            url,
            dest,
            headers,
            s,
            max_bytes=max_bytes,
            resolver=resolver,
            max_redirects=max_redirects,
            connection_factory=connection_factory,
        )
    return implementation(
        url,
        dest,
        headers,
        s,
        max_bytes=max_bytes,
        resolver=resolver,
        max_redirects=max_redirects,
        connection_factory=connection_factory,
        safe_get_fn=_safe_get,
        declared_size_fn=_declared_size,
    )


_OMITTED = object()


def _download_video_signature(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    *,
    max_bytes: int = REMOTE_VIDEO_MAX_BYTES,
    resolver: Callable[[str, int], list[str]] = _resolve_host,
    max_redirects: int = MAX_VIDEO_REDIRECTS,
    connection_factory=create_pinned_connection,
) -> Path:
    raise AssertionError("signature template is not callable")


_DOWNLOAD_VIDEO_SIGNATURE = inspect.signature(_download_video_signature)


def download_video(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    *,
    max_bytes: int = _OMITTED,
    resolver: Callable[[str, int], list[str]] = _OMITTED,
    max_redirects: int = _OMITTED,
    connection_factory=_OMITTED,
) -> Path:
    implementation = douyin_download.download_video
    effective_max_bytes = REMOTE_VIDEO_MAX_BYTES if max_bytes is _OMITTED else max_bytes
    effective_resolver = _resolve_host if resolver is _OMITTED else resolver
    effective_max_redirects = (
        MAX_VIDEO_REDIRECTS if max_redirects is _OMITTED else max_redirects
    )
    effective_connection_factory = (
        create_pinned_connection
        if connection_factory is _OMITTED
        else connection_factory
    )
    forwarded = {
        "session": session,
        "max_bytes": effective_max_bytes,
        "resolver": effective_resolver,
        "max_redirects": effective_max_redirects,
        "connection_factory": effective_connection_factory,
    }
    if implementation is not _DOWNLOAD_VIDEO_IMPLEMENTATION:
        return implementation(url, dest, **forwarded)
    return implementation(
        url,
        dest,
        **forwarded,
        mobile_ua=MOBILE_UA,
        safe_get_fn=_safe_get,
        download_whole_fn=_download_whole,
        declared_size_fn=_declared_size,
    )


download_video.__signature__ = _DOWNLOAD_VIDEO_SIGNATURE
