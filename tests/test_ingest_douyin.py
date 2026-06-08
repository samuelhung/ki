"""Tests for douyin share link parsing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ingest.douyin import parse_share_text, download_video, extract_first_url


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

    @patch("ingest.douyin.requests")
    def test_parses_valid_share_text(self, mock_requests):
        """Parse a valid douyin share text and return video info."""
        # First GET: follow short link redirect
        redirect_resp = MagicMock()
        redirect_resp.url = "https://www.douyin.com/video/v1234567890"
        redirect_resp.raise_for_status = lambda: None

        # Second GET: iesdouyin page with _ROUTER_DATA
        page_resp = MagicMock()
        router_json = json.dumps(self.FAKE_ROUTER_DATA, ensure_ascii=False)
        page_resp.text = f'<html><script>window._ROUTER_DATA = {router_json};</script></html>'
        page_resp.raise_for_status = lambda: None

        mock_requests.Session = MagicMock  # not used
        mock_requests.get.side_effect = [redirect_resp, page_resp]

        share = "看看这个 https://v.douyin.com/abc123/ 有意思"
        info = parse_share_text(share)

        assert info["video_id"] == "v1234567890"
        assert "测试视频标题" in info["platform_title"]
        assert "aweme.snssdk.com" in info["download_url"]
        # download_url should have playwm replaced with play
        assert "playwm" not in info["download_url"]

    @patch("ingest.douyin.requests")
    def test_raises_when_no_video_url_found(self, mock_requests):
        """Share text without a douyin URL should raise ValueError."""
        with pytest.raises(ValueError, match="未找到抖音分享链接"):
            parse_share_text("just chatting, no link here")

    @patch("ingest.douyin.requests")
    def test_raises_when_page_has_no_router_data(self, mock_requests):
        """Page without _ROUTER_DATA should raise RuntimeError."""
        redirect_resp = MagicMock()
        redirect_resp.url = "https://www.douyin.com/video/v1234567890"
        redirect_resp.raise_for_status = lambda: None

        page_resp = MagicMock()
        page_resp.text = "<html>no data here</html>"
        page_resp.raise_for_status = lambda: None

        mock_requests.get.side_effect = [redirect_resp, page_resp]

        with pytest.raises(RuntimeError, match="_ROUTER_DATA"):
            parse_share_text("https://v.douyin.com/abc123/")


class TestDownloadVideo:
    @patch("ingest.douyin.requests")
    def test_downloads_video_to_path(self, mock_requests, tmp_path: Path):
        """Video download writes content to the destination file."""
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.iter_content = lambda chunk_size: [b"fake-video-data"]
        mock_requests.get.return_value = resp

        dest = tmp_path / "video.mp4"
        result = download_video("https://example.com/video.mp4", dest)

        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == b"fake-video-data"
