import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import main
from zhiji_backend.main import app
from zhiji_backend.security.artifacts import PinnedFileResponse, open_regular_under


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
        ("HEAD", {}, 200, b"", "10", None),
        ("HEAD", {"Range": "bytes=2-5"}, 206, b"", "4", "bytes 2-5/10"),
        ("GET", {"Range": "bytes=99-100"}, 416, b"", "0", "bytes */10"),
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
