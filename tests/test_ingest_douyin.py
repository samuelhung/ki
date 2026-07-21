"""Tests for douyin share link parsing."""

from __future__ import annotations

import json
import sys
from collections import UserDict
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zhiji_backend.ingest.douyin import (
    download_video,
    extract_first_url,
    is_trusted_365yg_url,
    parse_share_text,
)


def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


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
    @patch("zhiji_backend.ingest.douyin.requests")
    def test_downloads_video_to_path(self, mock_requests, tmp_path: Path):
        """Video download writes content to the destination file."""
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.iter_content = lambda chunk_size: [b"fake-video-data"]
        mock_requests.Session.return_value.get.return_value = resp

        dest = tmp_path / "video.mp4"
        result = download_video("https://example.com/video.mp4", dest, resolver=public_resolver)

        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == b"fake-video-data"

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_rejects_content_length_over_limit_and_removes_partial(self, mock_requests, tmp_path: Path):
        resp = MagicMock()
        resp.headers = {"Content-Length": "6"}
        resp.raise_for_status = lambda: None
        mock_requests.Session.return_value.get.return_value = resp
        dest = tmp_path / "large.mp4"

        with pytest.raises(ValueError, match="大小"):
            download_video("https://example.com/video.mp4", dest, max_bytes=5, resolver=public_resolver)

        assert not dest.exists()

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_rejects_actual_bytes_over_limit_and_removes_partial(self, mock_requests, tmp_path: Path):
        resp = MagicMock()
        resp.headers = {}
        resp.raise_for_status = lambda: None
        resp.iter_content = lambda chunk_size: [b"abc", b"def"]
        mock_requests.Session.return_value.get.return_value = resp
        dest = tmp_path / "large.mp4"

        with pytest.raises(ValueError, match="大小"):
            download_video("https://example.com/video.mp4", dest, max_bytes=5, resolver=public_resolver)

        assert not dest.exists()

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_range_fallback_remains_bounded(self, mock_requests, tmp_path: Path):
        range_resp = MagicMock(status_code=206)
        range_resp.headers = {"Content-Length": "3"}
        range_resp.iter_content = lambda chunk_size: [b"abc"]
        session = mock_requests.Session.return_value
        session.get.side_effect = [OSError("whole failed"), range_resp]
        dest = tmp_path / "fallback.mp4"

        result = download_video(
            "https://example.com/video.mp4",
            dest,
            max_bytes=3,
            resolver=public_resolver,
        )

        assert result == dest
        assert dest.read_bytes() == b"abc"

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_range_fallback_stops_when_server_ignores_range(self, mock_requests, tmp_path: Path):
        whole = b"x" * (1024 * 1024)
        range_resp = MagicMock(status_code=200)
        range_resp.headers = {"Content-Length": str(len(whole))}
        range_resp.iter_content = lambda chunk_size: [whole]
        session = mock_requests.Session.return_value
        session.get.side_effect = [OSError("whole failed"), range_resp]
        dest = tmp_path / "fallback.mp4"

        download_video(
            "https://example.com/video.mp4",
            dest,
            max_bytes=len(whole),
            resolver=public_resolver,
        )

        assert dest.read_bytes() == whole
        assert session.get.call_count == 2

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_content_length_mapping_is_enforced(self, mock_requests, tmp_path: Path):
        resp = MagicMock()
        resp.headers = UserDict({"Content-Length": "6"})
        resp.raise_for_status = lambda: None
        mock_requests.Session.return_value.get.return_value = resp

        with pytest.raises(ValueError, match="大小"):
            download_video(
                "https://example.com/video.mp4",
                tmp_path / "large.mp4",
                max_bytes=5,
                resolver=public_resolver,
            )

    def test_rejects_non_http_download_protocol(self, tmp_path: Path):
        with pytest.raises(ValueError, match="协议"):
            download_video(
                "file:///tmp/video.mp4",
                tmp_path / "video.mp4",
                max_bytes=5,
                resolver=public_resolver,
            )

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_rejects_redirect_to_private_host(self, mock_requests, tmp_path: Path):
        redirect = MagicMock(status_code=302)
        redirect.headers = {"Location": "http://internal.example/video.mp4"}
        session = mock_requests.Session.return_value
        session.get.return_value = redirect

        def resolver(host: str, port: int) -> list[str]:
            return ["127.0.0.1"] if host == "internal.example" else ["93.184.216.34"]

        with pytest.raises(ValueError, match="公网"):
            download_video("https://example.com/video.mp4", tmp_path / "video.mp4", resolver=resolver)

        assert session.get.call_count == 1

    @patch("zhiji_backend.ingest.douyin.requests")
    def test_rejects_redirect_loop(self, mock_requests, tmp_path: Path):
        redirect = MagicMock(status_code=302)
        redirect.headers = {"Location": "/video.mp4"}
        session = mock_requests.Session.return_value
        session.get.return_value = redirect

        with pytest.raises(ValueError, match="重定向"):
            download_video(
                "https://example.com/video.mp4",
                tmp_path / "video.mp4",
                resolver=public_resolver,
                max_redirects=2,
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
