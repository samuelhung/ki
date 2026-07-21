"""Media extraction — ffmpeg audio extraction from video files."""

from __future__ import annotations

import shutil
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

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg executable not found")

    try:
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-probesize", "10M",
                "-analyzeduration", "10M",
                "-protocol_whitelist", "file,pipe",
                "-i", str(video_path),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(dest_audio),
            ],
            check=True,
            capture_output=True,
        )
    except BaseException:
        dest_audio.unlink(missing_ok=True)
        raise
    return dest_audio
