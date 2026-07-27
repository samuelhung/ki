"""Security and compatibility tests for pinned remote transport."""

from __future__ import annotations

import ssl
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from zhiji_backend.ingest import douyin, remote_transport


class Response:
    def __init__(self, *, status_code=200, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks
        self.close_calls = 0

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        self.close_calls += 1


class Connection:
    def __init__(self, responses, requests_seen):
        self._responses = responses
        self._requests_seen = requests_seen

    def get(self, target, *, headers, timeout):
        self._requests_seen.append((target, dict(headers), timeout))
        return self._responses.pop(0)


def test_validate_remote_url_accepts_mixed_answers_but_keeps_only_public_ips():
    target = remote_transport._validate_remote_url(
        "https://video.example.com/file.mp4",
        resolver=lambda _host, _port: ["127.0.0.1", "93.184.216.34"],
    )

    assert target.public_ips == ("93.184.216.34",)


def test_safe_get_filters_cookies_again_for_redirect_target():
    session = requests.Session()
    session.cookies.set("origin", "one", domain="origin.example", path="/")
    session.cookies.set("cdn", "two", domain="cdn.example", path="/")
    redirect = Response(
        status_code=302,
        headers={"Location": "https://cdn.example/video.mp4"},
    )
    responses = [redirect, Response()]
    requests_seen = []

    def connection_factory(_scheme, _ip, _port, _hostname):
        return Connection(responses, requests_seen)

    response = remote_transport._safe_get(
        session,
        "https://origin.example/start",
        headers={"User-Agent": "test"},
        timeout=(1, 2),
        resolver=lambda _host, _port: ["93.184.216.34"],
        max_redirects=2,
        connection_factory=connection_factory,
    )

    assert requests_seen[0][1]["Cookie"] == "origin=one"
    assert requests_seen[1][1]["Cookie"] == "cdn=two"
    assert "origin=one" not in requests_seen[1][1]["Cookie"]
    assert redirect.close_calls == 1
    response.close()


def test_douyin_pinned_connection_uses_facade_pool_at_call_time(monkeypatch):
    pool_cls = MagicMock()
    monkeypatch.setattr(douyin, "HTTPSConnectionPool", pool_cls)

    douyin.create_pinned_connection("https", "93.184.216.34", 443, "video.example.com")

    pool_cls.assert_called_once_with(
        "93.184.216.34",
        port=443,
        assert_hostname="video.example.com",
        server_hostname="video.example.com",
        cert_reqs=ssl.CERT_REQUIRED,
        maxsize=1,
        block=True,
    )


def test_douyin_pinned_connection_uses_facade_response_wrapper_at_call_time(
    monkeypatch,
):
    wrapped = object()

    class ResponseWrapper:
        def __new__(cls, response, pool):
            assert response.status == 200
            assert pool is pool_instance
            return wrapped

    pool_instance = MagicMock()
    pool_instance.urlopen.return_value = MagicMock(status=200, headers={})
    pool_cls = MagicMock(return_value=pool_instance)
    monkeypatch.setattr(douyin, "HTTPConnectionPool", pool_cls)
    monkeypatch.setattr(douyin, "_PinnedResponse", ResponseWrapper)

    connection = douyin.create_pinned_connection(
        "http", "93.184.216.34", 80, "video.example.com"
    )

    assert connection.get("/video.mp4", headers={}, timeout=(1, 2)) is wrapped


def test_douyin_download_uses_facade_defaults_and_helpers_at_call_time(
    tmp_path: Path, monkeypatch
):
    destination = tmp_path / "video.mp4"
    calls = []
    resolver = MagicMock()
    connection_factory = MagicMock()
    safe_get = MagicMock()

    def whole_file(url, dest, headers, session, **kwargs):
        calls.append((url, dest, headers, session, kwargs))
        dest.write_bytes(b"video")
        return True

    monkeypatch.setattr(douyin, "REMOTE_VIDEO_MAX_BYTES", 321)
    monkeypatch.setattr(douyin, "MAX_VIDEO_REDIRECTS", 4)
    monkeypatch.setattr(douyin, "MOBILE_UA", "facade-agent")
    monkeypatch.setattr(douyin, "_resolve_host", resolver)
    monkeypatch.setattr(douyin, "create_pinned_connection", connection_factory)
    monkeypatch.setattr(douyin, "_safe_get", safe_get)
    monkeypatch.setattr(douyin, "_download_whole", whole_file)

    assert (
        douyin.download_video("https://video.example/file.mp4", destination)
        == destination
    )

    assert calls == [
        (
            "https://video.example/file.mp4",
            destination,
            {
                "User-Agent": "facade-agent",
                "Referer": "https://www.douyin.com/",
                "Accept": "*/*",
            },
            None,
            {
                "max_bytes": 321,
                "resolver": resolver,
                "max_redirects": 4,
                "connection_factory": connection_factory,
            },
        )
    ]
    safe_get.assert_not_called()


def test_douyin_safe_get_uses_facade_requests_at_call_time(monkeypatch):
    requests_module = MagicMock()
    session = MagicMock()
    session.cookies = requests.cookies.RequestsCookieJar()
    response = Response()
    prepared = requests.Request("GET", "https://video.example/file.mp4").prepare()
    requests_module.Request.return_value.prepare.return_value = prepared
    monkeypatch.setattr(douyin, "requests", requests_module)

    result = douyin._safe_get(
        session,
        "https://video.example/file.mp4",
        headers={},
        timeout=(1, 2),
        resolver=lambda _host, _port: ["93.184.216.34"],
        max_redirects=0,
        connection_factory=lambda *_args: Connection([response], []),
    )

    assert result is response
    requests_module.Request.assert_called_once_with(
        "GET", "https://video.example/file.mp4"
    )


def test_douyin_download_uses_facade_declared_size_at_call_time(
    tmp_path: Path, monkeypatch
):
    response = Response(chunks=(b"video",))
    response.raise_for_status = lambda: None
    monkeypatch.setattr(douyin, "_declared_size", lambda _response: 6)

    with pytest.raises(ValueError, match="大小"):
        douyin.download_video(
            "https://video.example/file.mp4",
            tmp_path / "video.mp4",
            max_bytes=5,
            resolver=lambda _host, _port: ["93.184.216.34"],
            connection_factory=lambda *_args: Connection([response], []),
        )


def test_douyin_safe_get_uses_facade_redirect_statuses_at_call_time(monkeypatch):
    redirect = Response(status_code=299, headers={"Location": "/final.mp4"})
    final = Response()
    responses = [redirect, final]
    requests_seen = []
    monkeypatch.setattr(douyin, "_REDIRECT_STATUSES", {299})

    result = douyin._safe_get(
        None,
        "https://video.example/start",
        headers={},
        timeout=(1, 2),
        resolver=lambda _host, _port: ["93.184.216.34"],
        max_redirects=1,
        connection_factory=lambda *_args: Connection(responses, requests_seen),
    )

    assert result is final
    assert redirect.close_calls == 1
    assert [target for target, _headers, _timeout in requests_seen] == [
        "/start",
        "/final.mp4",
    ]
