"""Ingest pipeline — orchestrates multi-step media and document ingestion."""

from __future__ import annotations

from enum import Enum


class Step(Enum):
    PARSE_DOUYIN = "parse_douyin"
    DOWNLOAD_VIDEO = "download_video"
    EXTRACT_AUDIO = "extract_audio"
    UPLOAD_TOS = "upload_tos"
    TRANSCRIBE = "transcribe"
    PROCESS_DOC = "process_document"


PIPELINES: dict[str, list[Step]] = {
    "douyin_share": [
        Step.PARSE_DOUYIN,
        Step.DOWNLOAD_VIDEO,
        Step.EXTRACT_AUDIO,
        Step.UPLOAD_TOS,
        Step.TRANSCRIBE,
    ],
    "video_file": [
        Step.EXTRACT_AUDIO,
        Step.UPLOAD_TOS,
        Step.TRANSCRIBE,
    ],
    "audio_file": [
        Step.UPLOAD_TOS,
        Step.TRANSCRIBE,
    ],
    "document": [
        Step.PROCESS_DOC,
    ],
}
