"""Tests for media extraction (ffmpeg audio extraction from video)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ingest.media import extract_audio


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
