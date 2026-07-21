"""Tests for douyin share link parsing."""

from __future__ import annotations

import json
import ssl
import sys
from collections import UserDict
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zhiji_backend.ingest.douyin import (
    download_video,
    extract_first_url,
    is_trusted_365yg_url,
    parse_share_text,
    create_pinned_connection,
)


def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


class PinnedResponse:
    def __init__(self, chunks, *, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True


class PinnedConnection:
    def __init__(self, responses, requests_seen):
        self.responses = responses
        self.requests_seen = requests_seen

    def get(self, target, *, headers, timeout):
        self.requests_seen.append({"target": target, "headers": dict(headers), "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def pinned_factory(responses, requests_seen=None, connected_ips=None):
    requests_seen = requests_seen if requests_seen is not None else []
    connected_ips = connected_ips if connected_ips is not None else []

    def factory(scheme: str, ip: str, port: int, hostname: str):
        connected_ips.append(ip)
        return PinnedConnection(responses, requests_seen)

    return factory


class TestExtractFirstUrl:
    def test_extracts_v_douyin_url(self):
        text = "4.69 复制打开抖音，看看【雪野】的作品 https://v.douyin.com/FlCJk06WShI/ haha"
        assert extract_first_url(text) == "https://v.douyin.com/FlCJk06WShI"

    def test_returns_empty_when_no_url(self):
        assert extract_first_url("just some text") == ""

    def test_handles_trailing_punctuation(self):
        text = "看看 [视频](https://v.douyin.com/abc123/) 好玩"
        assert "v.douyin.com/abc123" in extract_first_url(text)


class TestParseShareText:
    FAKE_ROUTER_DATA = {
        "loaderData": {
            "video_(id)/page": {
                "videoInfoRes": {
                    "item_list": [{
                        "desc": "测试视频标题",
                        "video": {
                            "play_addr": {
                                "url_list": [
                                    "https://aweme.snssdk.com/playwm/video_123"
                                ]
                            }
                        }
                    }]
                }
            }
        }
    }

    def _mock_redirect(self, share_url: str, video_id: str = "v1234567890"):
        """Create a mock that simulates douyin short-link redirect."""
        mock = MagicMock()
        mock.url = f"https://www.douyin.com/video/{video_id}?foo=bar"
        mock.raise_for_status = lambda: None
        return {"get.return_value": mock}

    def _mock_page(self, video_id: str = "v1234567890"):
        """Create a mock for the iesdouyin page response."""
        router_json = json.dumps(self.FAKE_ROUTER_DATA, ensure_ascii=False)
        page = f'<html><script>window._ROUTER_DATA = {router_json};</script></html>'
        mock = MagicMock()
        mock.text = page
        mock.raise_for_status = lambda: None
        return {"get.return_value": mock}

    @staticmethod
    def _response(*, url="", text="", json_data=None, status_code=200, headers=None):
        resp = MagicMock()
        resp.url = url
        resp.text = text
        resp.status_code = status_code
        resp.headers = headers or {}
        resp.raise_for_status = lambda: None
        if json_data is None:
            resp.json.side_effect = ValueError("empty response")
        else:
            resp.json.return_value = json_data
        return resp

    @patch("zhiji_backend.ingest.douyin.requests.Session")
    def test_parses_valid_share_text_from_detail_api(self, mock_session_cls):
        """Parse a valid douyin share text from the detail API."""
        # First GET: follow short link redirect
        redirect_resp = self._response(url="https://www.douyin.com/video/v1234567890")

        detail_resp = self._response(json_data={
            "aweme_detail": {
                "desc": "测试视频标题",
                "video": {
                    "play_addr": {
                        "url_list": ["https://aweme.snssdk.com/playwm/video_123"]
                    }
                },
            }
        }, text='{"aweme_detail":{}}', headers={"content-type": "application/json"})

        session = MagicMock()
        session.get.side_effect = [redirect_resp, detail_resp]
        mock_session_cls.return_value = session

        share = "看看这个 https://v.douyin.com/abc123/ 有意思"
        info = parse_share_text(share)

        assert info["video_id"] == "v1234567890"
        assert "测试视频标题" in info["platform_title"]
        assert "aweme.snssdk.com" in info["download_url"]
        # download_url should have playwm replaced with play
        assert "playwm" not in info["download_url"]

    @patch("zhiji_backend.ingest.douyin.requests.Session")
    def test_falls_back_to_landing_page_when_detail_api_is_empty(self, mock_session_cls):
        """Use embedded landing-page metadata when the detail API returns an empty JSON body."""
        page_json = json.dumps({
            "extra": {"logid": "fake"},
            "item_list": [{
                "aweme_id": "7656011545876516147",
                "desc": "真翻盘了吗？看懂 Intel 翻身",
                "video": {
                    "play_addr": {
                        "url_list": [
                            "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0200"
                        ]
                    }
                },
            }],
        }, ensure_ascii=False)
        landing_html = f'<html><script>window.__DATA__={{"videoInfoRes":{page_json}}};</script></html>'
        redirect_resp = self._response(
            url="https://www.iesdouyin.com/share/video/7656011545876516147/",
            text=landing_html,
        )
        detail_resp = self._response(
            text="",
            headers={"content-type": "application/json"},
        )

        session = MagicMock()
        session.get.side_effect = [redirect_resp, detail_resp]
        mock_session_cls.return_value = session

        info = parse_share_text("https://v.douyin.com/Rv8VNZLU-88/")

        assert info["video_id"] == "7656011545876516147"
        assert info["platform_title"] == "真翻盘了吗？看懂 Intel 翻身"
        assert info["download_url"] == "https://aweme.snssdk.com/aweme/v1/play/?video_id=v0200"

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_raises_when_no_video_url_found(self, mock_requests):
        """Share text without a douyin URL should raise ValueError."""
        with pytest.raises(ValueError, match="未找到抖音分享链接"):
            parse_share_text("just chatting, no link here")

    @patch("zhiji_backend.ingest.douyin.requests.Session")
    def test_raises_when_no_detail_or_page_metadata(self, mock_session_cls):
        """Raise a clear error when neither API nor landing page has metadata."""
        redirect_resp = self._response(
            url="https://www.douyin.com/video/v1234567890",
            text="<html>no data here</html>",
        )
        detail_resp = self._response(text="", headers={"content-type": "application/json"})
        session = MagicMock()
        session.get.side_effect = [redirect_resp, detail_resp]
        mock_session_cls.return_value = session

        with pytest.raises(RuntimeError, match="videoInfoRes"):
            parse_share_text("https://v.douyin.com/abc123/")

    def test_365yg_trust_uses_exact_hostname_boundaries(self):
        assert is_trusted_365yg_url("https://365yg.com/video")
        assert is_trusted_365yg_url("https://v3.365yg.com/video")
        assert not is_trusted_365yg_url("https://365yg.com.evil.example/video")
        assert not is_trusted_365yg_url("https://evil365yg.com/video")


class TestDownloadVideo:
    @patch("zhiji_backend.ingest.douyin.HTTPSConnectionPool")
    def test_https_pinned_connection_preserves_certificate_hostname_and_sni(self, pool_cls):
        create_pinned_connection("https", "93.184.216.34", 443, "video.example.com")

        pool_cls.assert_called_once_with(
            "93.184.216.34",
            port=443,
            assert_hostname="video.example.com",
            server_hostname="video.example.com",
            cert_reqs=ssl.CERT_REQUIRED,
            maxsize=1,
            block=True,
        )

    def test_dns_rebinding_private_result_is_never_connected(self, tmp_path: Path):
        resolutions = iter([["93.184.216.34"], ["127.0.0.1"]])
        resolver_calls = []
        connected_ips = []
        requests_seen = []
        responses = [OSError("public connection failed")]

        def resolver(host: str, port: int) -> list[str]:
            resolver_calls.append((host, port))
            return next(resolutions)

        def connection_factory(scheme: str, ip: str, port: int, hostname: str):
            connected_ips.append(ip)
            return PinnedConnection(responses, requests_seen)

        dest = tmp_path / "video.mp4"
        with pytest.raises(ValueError, match="公网"):
            download_video(
                "https://video.example.com/video.mp4",
                dest,
                resolver=resolver,
                connection_factory=connection_factory,
            )

        assert not dest.exists()
        assert connected_ips == ["93.184.216.34"]
        assert "127.0.0.1" not in connected_ips
        assert resolver_calls == [
            ("video.example.com", 443),
            ("video.example.com", 443),
        ]
        assert requests_seen[0]["headers"]["Host"] == "video.example.com"

    def test_session_cookies_are_copied_to_pinned_request_headers(self, tmp_path: Path):
        session = requests.Session()
        session.cookies.set("sid", "cookie-value", domain="video.example.com", path="/")
        requests_seen = []
        responses = [PinnedResponse([b"video"])]

        def connection_factory(scheme: str, ip: str, port: int, hostname: str):
            return PinnedConnection(responses, requests_seen)

        download_video(
            "https://video.example.com/video.mp4",
            tmp_path / "video.mp4",
            session=session,
            resolver=public_resolver,
            connection_factory=connection_factory,
        )

        assert requests_seen[0]["headers"]["Cookie"] == "sid=cookie-value"

    def test_downloads_video_to_path(self, tmp_path: Path):
        """Video download writes content to the destination file."""
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.iter_content = lambda chunk_size: [b"fake-video-data"]
        factory = pinned_factory([resp])

        dest = tmp_path / "video.mp4"
        result = download_video(
            "https://example.com/video.mp4",
            dest,
            resolver=public_resolver,
            connection_factory=factory,
        )

        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == b"fake-video-data"

    def test_rejects_content_length_over_limit_and_removes_partial(self, tmp_path: Path):
        resp = PinnedResponse([], headers={"Content-Length": "6"})
        factory = pinned_factory([resp])
        dest = tmp_path / "large.mp4"

        with pytest.raises(ValueError, match="大小"):
            download_video(
                "https://example.com/video.mp4",
                dest,
                max_bytes=5,
                resolver=public_resolver,
                connection_factory=factory,
            )

        assert not dest.exists()
        assert resp.closed

    def test_rejects_actual_bytes_over_limit_and_removes_partial(self, tmp_path: Path):
        resp = PinnedResponse([b"abc", b"def"])
        factory = pinned_factory([resp])
        dest = tmp_path / "large.mp4"

        with pytest.raises(ValueError, match="大小"):
            download_video(
                "https://example.com/video.mp4",
                dest,
                max_bytes=5,
                resolver=public_resolver,
                connection_factory=factory,
            )

        assert not dest.exists()
        assert resp.closed

    def test_range_fallback_remains_bounded(self, tmp_path: Path):
        range_resp = MagicMock(status_code=206)
        range_resp.headers = {"Content-Length": "3"}
        range_resp.iter_content = lambda chunk_size: [b"abc"]
        factory = pinned_factory([OSError("whole failed"), range_resp])
        dest = tmp_path / "fallback.mp4"

        result = download_video(
            "https://example.com/video.mp4",
            dest,
            max_bytes=3,
            resolver=public_resolver,
            connection_factory=factory,
        )

        assert result == dest
        assert dest.read_bytes() == b"abc"

    def test_range_fallback_stops_when_server_ignores_range(self, tmp_path: Path):
        whole = b"x" * (1024 * 1024)
        range_resp = MagicMock(status_code=200)
        range_resp.headers = {"Content-Length": str(len(whole))}
        range_resp.iter_content = lambda chunk_size: [whole]
        requests_seen = []
        factory = pinned_factory([OSError("whole failed"), range_resp], requests_seen=requests_seen)
        dest = tmp_path / "fallback.mp4"

        download_video(
            "https://example.com/video.mp4",
            dest,
            max_bytes=len(whole),
            resolver=public_resolver,
            connection_factory=factory,
        )

        assert dest.read_bytes() == whole
        assert len(requests_seen) == 2

    def test_content_length_mapping_is_enforced(self, tmp_path: Path):
        resp = MagicMock()
        resp.headers = UserDict({"Content-Length": "6"})
        resp.raise_for_status = lambda: None
        factory = pinned_factory([resp])

        with pytest.raises(ValueError, match="大小"):
            download_video(
                "https://example.com/video.mp4",
                tmp_path / "large.mp4",
                max_bytes=5,
                resolver=public_resolver,
                connection_factory=factory,
            )

    def test_rejects_non_http_download_protocol(self, tmp_path: Path):
        with pytest.raises(ValueError, match="协议"):
            download_video(
                "file:///tmp/video.mp4",
                tmp_path / "video.mp4",
                max_bytes=5,
                resolver=public_resolver,
            )

    def test_rejects_redirect_to_private_host(self, tmp_path: Path):
        redirect = PinnedResponse([], status_code=302, headers={"Location": "http://internal.example/video.mp4"})
        requests_seen = []
        factory = pinned_factory([redirect], requests_seen=requests_seen)

        def resolver(host: str, port: int) -> list[str]:
            return ["127.0.0.1"] if host == "internal.example" else ["93.184.216.34"]

        with pytest.raises(ValueError, match="公网"):
            download_video(
                "https://example.com/video.mp4",
                tmp_path / "video.mp4",
                resolver=resolver,
                connection_factory=factory,
            )

        assert len(requests_seen) == 1

    def test_rejects_redirect_loop(self, tmp_path: Path):
        redirect = PinnedResponse([], status_code=302, headers={"Location": "/video.mp4"})
        factory = pinned_factory([redirect])

        with pytest.raises(ValueError, match="重定向"):
            download_video(
                "https://example.com/video.mp4",
                tmp_path / "video.mp4",
                resolver=public_resolver,
                max_redirects=2,
                connection_factory=factory,
            )

    @pytest.mark.parametrize(
        "url",
        [
            "https://user:pass@example.com/video.mp4",
            "https://example.com:99999/video.mp4",
        ],
    )
    def test_rejects_credentials_and_invalid_ports(self, tmp_path: Path, url: str):
        with pytest.raises(ValueError):
            download_video(url, tmp_path / "video.mp4", resolver=public_resolver)
