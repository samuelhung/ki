"""Media extraction — ffmpeg audio extraction from video files."""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_audio(video_path: Path, dest_audio: Path) -> Path:
    """Extract audio track from video file as 16kHz mono WAV.

    Args:
        video_path: Path to source video file.
        dest_audio: Destination path for extracted audio (.wav).

    Returns:
        Path to the extracted audio file.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails.
        FileNotFoundError: If video_path does not exist.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",                # no video
            "-acodec", "pcm_s16le",
            "-ar", "16000",       # 16kHz sample rate
            "-ac", "1",           # mono
            str(dest_audio),
        ],
        check=True,
        capture_output=True,
    )
    return dest_audio
