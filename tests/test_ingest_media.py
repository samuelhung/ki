"""Tests for media extraction (ffmpeg audio extraction from video)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zhiji_backend.ingest.media import (
    FFMPEG_MAX_ALLOC_BYTES,
    FFMPEG_MAX_OUTPUT_BYTES,
    FFMPEG_TIMEOUT_SECONDS,
    extract_audio,
)


def _make_test_video(tmp_path: Path) -> Path:
    """Generate a 1-second test video with ffmpeg."""
    video = tmp_path / "test.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=duration=1:size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest", str(video),
        ],
        check=True, capture_output=True,
    )
    return video


def test_extract_audio_from_video(tmp_path: Path):
    """ffmpeg extracts audio from video into a WAV file."""
    video = _make_test_video(tmp_path)
    assert video.exists()

    dest = tmp_path / "output.wav"
    result = extract_audio(video, dest)

    assert result == dest
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_extract_audio_missing_input_raises():
    """Non-existent input file should raise an error."""
    with pytest.raises((FileNotFoundError, subprocess.CalledProcessError, RuntimeError)):
        extract_audio(Path("/nonexistent/video.mp4"), Path("/tmp/out.wav"))


@patch("zhiji_backend.ingest.media.shutil.which", return_value="/opt/local/bin/ffmpeg")
@patch("zhiji_backend.ingest.media.subprocess.run")
def test_extract_audio_uses_hardened_ffmpeg_argv(mock_run, mock_which, tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    dest = tmp_path / "output.wav"

    extract_audio(video, dest)

    argv = mock_run.call_args.args[0]
    assert argv[0] == "/opt/local/bin/ffmpeg"
    assert argv[1:6] == ["-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    input_index = argv.index("-i")
    assert argv[argv.index("-protocol_whitelist") + 1] == "file,pipe"
    assert argv.index("-protocol_whitelist") < input_index
    assert argv.index("-probesize") < input_index
    assert argv.index("-analyzeduration") < input_index
    assert argv[argv.index("-max_alloc") + 1] == str(FFMPEG_MAX_ALLOC_BYTES)
    assert argv.index("-max_alloc") < input_index
    assert argv[argv.index("-threads") + 1] == "1"
    assert argv[argv.index("-filter_threads") + 1] == "1"
    assert argv[argv.index("-filter_complex_threads") + 1] == "1"
    assert argv[argv.index("-fs") + 1] == str(FFMPEG_MAX_OUTPUT_BYTES)
    assert argv.index("-fs") > input_index
    assert mock_run.call_args.kwargs["timeout"] == FFMPEG_TIMEOUT_SECONDS
    assert mock_run.call_args.kwargs["start_new_session"] is True
    assert "preexec_fn" not in mock_run.call_args.kwargs


@patch("zhiji_backend.ingest.media.shutil.which", return_value="/opt/local/bin/ffmpeg")
def test_extract_audio_removes_partial_destination_on_failure(mock_which, tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    dest = tmp_path / "output.wav"

    def fail(*args, **kwargs):
        dest.write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, args[0])

    with patch("zhiji_backend.ingest.media.subprocess.run", side_effect=fail):
        with pytest.raises(subprocess.CalledProcessError):
            extract_audio(video, dest)

    assert not dest.exists()


@patch("zhiji_backend.ingest.media.shutil.which", return_value="/opt/local/bin/ffmpeg")
def test_extract_audio_removes_partial_destination_on_timeout(mock_which, tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    dest = tmp_path / "output.wav"

    def timeout(*args, **kwargs):
        dest.write_bytes(b"partial")
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    with patch("zhiji_backend.ingest.media.subprocess.run", side_effect=timeout):
        with pytest.raises(subprocess.TimeoutExpired):
            extract_audio(video, dest, timeout_seconds=7, max_output_bytes=10)

    assert not dest.exists()


@patch("zhiji_backend.ingest.media.shutil.which", return_value="/opt/local/bin/ffmpeg")
def test_extract_audio_rejects_and_removes_oversized_output(mock_which, tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    dest = tmp_path / "output.wav"

    def oversize(*args, **kwargs):
        dest.write_bytes(b"12345")

    with patch("zhiji_backend.ingest.media.subprocess.run", side_effect=oversize):
        with pytest.raises(ValueError, match="大小"):
            extract_audio(video, dest, timeout_seconds=7, max_output_bytes=4)

    assert not dest.exists()


def test_extract_audio_uses_linux_prlimit_wrapper_when_available(tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    dest = tmp_path / "output.wav"

    def resolve(name: str):
        return {"ffmpeg": "/usr/bin/ffmpeg", "prlimit": "/usr/bin/prlimit"}.get(name)

    with patch("zhiji_backend.ingest.media.sys.platform", "linux"):
        with patch("zhiji_backend.ingest.media.shutil.which", side_effect=resolve):
            with patch("zhiji_backend.ingest.media.subprocess.run") as run:
                extract_audio(video, dest)

    argv = run.call_args.args[0]
    assert argv[:4] == [
        "/usr/bin/prlimit",
        "--as=2147483648",
        "--cpu=300",
        "--",
    ]
    assert argv[4] == "/usr/bin/ffmpeg"
    assert "preexec_fn" not in run.call_args.kwargs
