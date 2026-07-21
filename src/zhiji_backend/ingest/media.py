"""Media extraction — ffmpeg audio extraction from video files."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


# 16 kHz mono PCM is about 32 KiB/s; 512 MiB permits roughly 4.5 hours.
FFMPEG_MAX_OUTPUT_BYTES = 512 * 1024 * 1024
FFMPEG_TIMEOUT_SECONDS = 300


def extract_audio(
    video_path: Path,
    dest_audio: Path,
    *,
    timeout_seconds: int = FFMPEG_TIMEOUT_SECONDS,
    max_output_bytes: int = FFMPEG_MAX_OUTPUT_BYTES,
) -> Path:
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
                "-fs", str(max_output_bytes),
                str(dest_audio),
            ],
            check=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        if dest_audio.exists() and dest_audio.stat().st_size > max_output_bytes:
            raise ValueError("ffmpeg 输出大小超过限制")
    except BaseException:
        dest_audio.unlink(missing_ok=True)
        raise
    return dest_audio
