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
    FFMPEG_TRUSTED_PATHS,
    _resolve_ffmpeg,
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


def test_resolve_ffmpeg_prefers_path_lookup():
    with patch(
        "zhiji_backend.ingest.media.shutil.which",
        return_value="/opt/local/bin/ffmpeg",
    ):
        assert _resolve_ffmpeg() == "/opt/local/bin/ffmpeg"


def test_resolve_ffmpeg_uses_intel_homebrew_fallback(tmp_path: Path):
    ffmpeg = tmp_path / "usr-local-ffmpeg"
    ffmpeg.write_bytes(b"binary")
    ffmpeg.chmod(0o755)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", (ffmpeg,)):
            assert _resolve_ffmpeg() == str(ffmpeg.resolve())


def test_resolve_ffmpeg_uses_apple_silicon_fallback_after_missing_intel(tmp_path: Path):
    missing = tmp_path / "missing-intel-ffmpeg"
    ffmpeg = tmp_path / "opt-homebrew-ffmpeg"
    ffmpeg.write_bytes(b"binary")
    ffmpeg.chmod(0o755)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch(
            "zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS",
            (missing, ffmpeg),
        ):
            assert _resolve_ffmpeg() == str(ffmpeg.resolve())


def test_resolve_ffmpeg_accepts_symlink_to_executable_file(tmp_path: Path):
    target = tmp_path / "ffmpeg-target"
    target.write_bytes(b"binary")
    target.chmod(0o755)
    candidate = tmp_path / "ffmpeg"
    candidate.symlink_to(target)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", (candidate,)):
            assert _resolve_ffmpeg() == str(target.resolve())


def test_resolve_ffmpeg_rejects_symlink_loop(tmp_path: Path):
    candidate = tmp_path / "ffmpeg"
    candidate.symlink_to(candidate)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", (candidate,)):
            assert _resolve_ffmpeg() is None


@pytest.mark.parametrize("kind", ["missing", "directory", "non_executable"])
def test_resolve_ffmpeg_rejects_unusable_trusted_candidates(tmp_path: Path, kind: str):
    candidate = tmp_path / "ffmpeg"
    if kind == "directory":
        candidate.mkdir()
    elif kind == "non_executable":
        candidate.write_bytes(b"binary")
        candidate.chmod(0o644)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", (candidate,)):
            assert _resolve_ffmpeg() is None


def test_ffmpeg_trusted_paths_cover_both_homebrew_prefixes():
    assert FFMPEG_TRUSTED_PATHS == (
        Path("/usr/local/bin/ffmpeg"),
        Path("/opt/homebrew/bin/ffmpeg"),
    )


def test_extract_audio_raises_when_no_ffmpeg_candidate_is_usable(tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", ()):
            with pytest.raises(RuntimeError, match="ffmpeg executable not found"):
                extract_audio(video, tmp_path / "output.wav")


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
