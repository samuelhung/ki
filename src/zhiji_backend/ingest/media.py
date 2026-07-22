"""Media extraction — ffmpeg audio extraction from video files."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


# 16 kHz mono PCM is about 32 KiB/s; 512 MiB permits roughly 4.5 hours.
FFMPEG_MAX_OUTPUT_BYTES = 512 * 1024 * 1024
FFMPEG_TIMEOUT_SECONDS = 300
FFMPEG_MAX_ALLOC_BYTES = 256 * 1024 * 1024
FFMPEG_ADDRESS_SPACE_BYTES = 2 * 1024 * 1024 * 1024
FFMPEG_CPU_SECONDS = 300


def _command_prefix(ffmpeg: str) -> list[str]:
    if sys.platform.startswith("linux"):
        prlimit = shutil.which("prlimit")
        if prlimit:
            return [
                prlimit,
                f"--as={FFMPEG_ADDRESS_SPACE_BYTES}",
                f"--cpu={FFMPEG_CPU_SECONDS}",
                "--",
                ffmpeg,
            ]
    return [ffmpeg]


def _process_isolation_kwargs() -> dict:
    if sys.platform == "win32":
        flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flag} if flag else {}
    return {"start_new_session": True}


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
                *_command_prefix(ffmpeg),
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-threads", "1",
                "-filter_threads", "1",
                "-filter_complex_threads", "1",
                "-probesize", "10M",
                "-analyzeduration", "10M",
                "-max_alloc", str(FFMPEG_MAX_ALLOC_BYTES),
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
            **_process_isolation_kwargs(),
        )
        if dest_audio.exists() and dest_audio.stat().st_size > max_output_bytes:
            raise ValueError("ffmpeg 输出大小超过限制")
    except BaseException:
        dest_audio.unlink(missing_ok=True)
        raise
    return dest_audio
