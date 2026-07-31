"""File-type detection contracts for content ingestion."""

from __future__ import annotations

from pathlib import Path

FILE_TYPE_MAP = {
    "document": {".md", ".txt", ".markdown", ".json", ".csv", ".log", ".pdf", ".epub"},
    "audio_file": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"},
    "video_file": {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mts", ".ts", ".flv"},
}


def detect_ingest_type(filename, *, file_type_map=FILE_TYPE_MAP):
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    return next(
        (kind for kind, extensions in file_type_map.items() if suffix in extensions),
        None,
    )
