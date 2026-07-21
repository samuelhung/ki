import asyncio
import email.utils
import os

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import main
from zhiji_backend.main import app
from zhiji_backend.security.artifacts import (
    PinnedFileResponse,
    _single_range,
    open_regular_under,
)


def _assert_fd_closed(fd: int) -> None:
    with pytest.raises(OSError):
        os.fstat(fd)


def test_ingest_artifact_symlink_swap_after_open_never_serves_external_bytes(
    tmp_path, monkeypatch
):
    ingest_root = tmp_path / "ingest"
    documents = ingest_root / "documents"
    documents.mkdir(parents=True)
    artifact = documents / "evt-race.pdf"
    artifact.write_bytes(b"inside-bytes")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"external-secret")
    real_open = main.open_regular_under

    def open_then_swap(root, *parts):
        opened = real_open(root, *parts)
        artifact.rename(documents / "original.pdf")
        artifact.symlink_to(outside)
        return opened

    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    monkeypatch.setattr(main, "open_regular_under", open_then_swap)

    response = TestClient(app).get("/ingest/documents/evt-race.pdf")

    assert response.status_code == 200
    assert response.content == b"inside-bytes"
    assert b"external-secret" not in response.content


@pytest.mark.parametrize(
    ("method", "headers", "status", "body", "content_length", "content_range"),
    [
        ("GET", {"Range": "bytes=2-5"}, 206, b"2345", "4", "bytes 2-5/10"),
        ("GET", {"Range": "bytes=4-"}, 206, b"456789", "6", "bytes 4-9/10"),
        ("HEAD", {}, 200, b"", "10", None),
        ("HEAD", {"Range": "bytes=2-5"}, 206, b"", "4", "bytes 2-5/10"),
        ("GET", {"Range": "bytes=99-100"}, 416, b"", "0", "bytes */10"),
        ("HEAD", {"Range": "bytes=99-100"}, 416, b"", "0", "bytes */10"),
    ],
)
def test_ingest_artifact_pinned_fd_range_head_and_error_close(
    tmp_path,
    monkeypatch,
    method,
    headers,
    status,
    body,
    content_length,
    content_range,
):
    ingest_root = tmp_path / "ingest"
    videos = ingest_root / "videos"
    videos.mkdir(parents=True)
    (videos / "evt-1.mp4").write_bytes(b"0123456789")
    captured_fds = []
    real_open = main.open_regular_under

    def capture_open(root, *parts):
        opened = real_open(root, *parts)
        captured_fds.append(opened.fd)
        return opened

    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    monkeypatch.setattr(main, "open_regular_under", capture_open)

    response = TestClient(app).request(
        method, "/ingest/videos/evt-1.mp4", headers=headers
    )

    assert response.status_code == status
    assert response.content == body
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == content_length
    assert response.headers.get("content-range") == content_range
    assert response.headers["content-type"] == "video/mp4"
    assert len(captured_fds) == 1
    _assert_fd_closed(captured_fds[0])


@pytest.mark.parametrize(
    "range_header",
    [
        "bytes=+1-2",
        "bytes= 1-2",
        "bytes=1 -2",
        "bytes=1- 2",
        "bytes=1-2 ",
        "bytes=1-2,4-5",
        "bytes=-",
        "bytes=--",
    ],
)
def test_malformed_ranges_return_416_and_close_fd(tmp_path, monkeypatch, range_header):
    ingest_root = tmp_path / "ingest"
    documents = ingest_root / "documents"
    documents.mkdir(parents=True)
    (documents / "evt-1.pdf").write_bytes(b"0123456789")
    captured_fds = []
    real_open = main.open_regular_under

    def capture_open(root, *parts):
        opened = real_open(root, *parts)
        captured_fds.append(opened.fd)
        return opened

    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    monkeypatch.setattr(main, "open_regular_under", capture_open)

    response = TestClient(app).get(
        "/ingest/documents/evt-1.pdf", headers={"Range": range_header}
    )

    assert response.status_code == 416
    assert response.content == b""
    assert response.headers["content-range"] == "bytes */10"
    _assert_fd_closed(captured_fds[0])


def test_range_parser_rejects_non_ascii_digits():
    assert _single_range("bytes=\u0661-2", 10) == (416, 0, -1)


def test_if_none_match_variants_return_304_and_close_fd(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    transcripts = ingest_root / "transcripts"
    transcripts.mkdir(parents=True)
    (transcripts / "evt-1.md").write_bytes(b"transcript")
    captured_fds = []
    real_open = main.open_regular_under

    def capture_open(root, *parts):
        opened = real_open(root, *parts)
        captured_fds.append(opened.fd)
        return opened

    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    monkeypatch.setattr(main, "open_regular_under", capture_open)
    client = TestClient(app)
    etag = client.get("/ingest/transcripts/evt-1.md").headers["etag"]
    _assert_fd_closed(captured_fds.pop())

    for value in (etag, f"W/{etag}", f'"other", W/{etag}', "*"):
        response = client.get(
            "/ingest/transcripts/evt-1.md", headers={"If-None-Match": value}
        )
        assert response.status_code == 304
        assert response.content == b""
        assert response.headers["etag"] == etag
        _assert_fd_closed(captured_fds.pop())


def test_if_modified_since_get_and_head_return_304_and_close_fd(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    summaries = ingest_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "evt-1.md").write_bytes(b"summary")
    captured_fds = []
    real_open = main.open_regular_under

    def capture_open(root, *parts):
        opened = real_open(root, *parts)
        captured_fds.append(opened.fd)
        return opened

    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    monkeypatch.setattr(main, "open_regular_under", capture_open)
    client = TestClient(app)
    last_modified = client.get("/ingest/summaries/evt-1.md").headers[
        "last-modified"
    ]
    _assert_fd_closed(captured_fds.pop())

    for method in ("GET", "HEAD"):
        response = client.request(
            method,
            "/ingest/summaries/evt-1.md",
            headers={"If-Modified-Since": last_modified},
        )
        assert response.status_code == 304
        assert response.content == b""
        _assert_fd_closed(captured_fds.pop())


def test_if_none_match_precedes_if_modified_since(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    audio = ingest_root / "audio"
    audio.mkdir(parents=True)
    (audio / "evt-1.mp3").write_bytes(b"audio")
    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)

    response = TestClient(app).get(
        "/ingest/audio/evt-1.mp3",
        headers={
            "If-None-Match": '"different"',
            "If-Modified-Since": "Wed, 31 Dec 2999 23:59:59 GMT",
        },
    )

    assert response.status_code == 200
    assert response.content == b"audio"


def test_if_range_controls_partial_or_full_response_and_closes_fd(tmp_path, monkeypatch):
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "zhiji.dmg").write_bytes(b"0123456789")
    captured_fds = []
    real_open = main.open_regular_under

    def capture_open(root, *parts):
        opened = real_open(root, *parts)
        captured_fds.append(opened.fd)
        return opened

    monkeypatch.setattr(main, "RELEASES_DIR", releases)
    monkeypatch.setattr(main, "open_regular_under", capture_open)
    client = TestClient(app)
    initial = client.get("/releases/zhiji.dmg")
    etag = initial.headers["etag"]
    last_modified = initial.headers["last-modified"]
    modified_second = int(email.utils.parsedate_to_datetime(last_modified).timestamp())
    past_modified = email.utils.formatdate(modified_second - 1, usegmt=True)
    future_modified = email.utils.formatdate(modified_second + 1, usegmt=True)
    _assert_fd_closed(captured_fds.pop())

    cases = [
        (etag, 206, b"2345"),
        (f"W/{etag}", 200, b"0123456789"),
        ('"different"', 200, b"0123456789"),
        (last_modified, 206, b"2345"),
        (past_modified, 200, b"0123456789"),
        (future_modified, 200, b"0123456789"),
        ("not-a-date", 200, b"0123456789"),
    ]
    for if_range, status, body in cases:
        response = client.get(
            "/releases/zhiji.dmg",
            headers={"Range": "bytes=2-5", "If-Range": if_range},
        )
        assert response.status_code == status
        assert response.content == body
        _assert_fd_closed(captured_fds.pop())


def test_release_artifact_uses_pinned_fd_and_closes_after_range(tmp_path, monkeypatch):
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "zhiji.dmg").write_bytes(b"release-data")
    captured_fds = []
    real_open = main.open_regular_under

    def capture_open(root, *parts):
        opened = real_open(root, *parts)
        captured_fds.append(opened.fd)
        return opened

    monkeypatch.setattr(main, "RELEASES_DIR", releases)
    monkeypatch.setattr(main, "open_regular_under", capture_open)

    response = TestClient(app).get(
        "/releases/zhiji.dmg", headers={"Range": "bytes=-4"}
    )

    assert response.status_code == 206
    assert response.content == b"data"
    assert response.headers["content-range"] == "bytes 8-11/12"
    assert len(captured_fds) == 1
    _assert_fd_closed(captured_fds[0])


def test_pinned_file_response_closes_fd_when_send_is_cancelled(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "artifact.bin").write_bytes(b"content")
    opened = open_regular_under(root, "artifact.bin")
    fd = opened.fd
    response = PinnedFileResponse(opened, filename="artifact.bin")

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.body":
            raise asyncio.CancelledError

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
    }

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(response(scope, receive, send))

    _assert_fd_closed(fd)


def test_pinned_file_response_stops_and_closes_on_http_disconnect(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "artifact.bin").write_bytes(b"content")
    opened = open_regular_under(root, "artifact.bin")
    fd = opened.fd
    response = PinnedFileResponse(opened, filename="artifact.bin")
    body_messages = []

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            body_messages.append(message["body"])

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
    }

    asyncio.run(response(scope, receive, send))

    assert body_messages == []
    _assert_fd_closed(fd)


def test_pinned_file_response_closes_fd_when_response_start_fails(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "artifact.bin").write_bytes(b"content")
    opened = open_regular_under(root, "artifact.bin")
    fd = opened.fd
    response = PinnedFileResponse(opened, filename="artifact.bin")

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        raise RuntimeError("send failed")

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
    }

    with pytest.raises(RuntimeError, match="send failed"):
        asyncio.run(response(scope, receive, send))

    _assert_fd_closed(fd)
