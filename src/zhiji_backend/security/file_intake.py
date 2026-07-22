"""Bounded file intake and content validation for user-controlled files."""

from __future__ import annotations

import json
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import HTTPException, UploadFile


MIB = 1024 * 1024
GIB = 1024 * MIB
CHUNK_SIZE = MIB

AUDIO_VIDEO_MAX_BYTES = 2 * GIB
DOCUMENT_MAX_BYTES = 200 * MIB
IMAGE_MAX_BYTES = 25 * MIB
OCR_PDF_MAX_BYTES = 100 * MIB
OCR_PDF_MAX_PAGES = 300
REMOTE_VIDEO_MAX_BYTES = 2 * GIB
MAX_ID3_TAG_BYTES = 16 * MIB


@dataclass(frozen=True)
class EpubLimits:
    max_entries: int = 5000
    max_expanded_total: int = 200 * MIB
    max_member: int = 25 * MIB
    max_ratio: int = 100
    max_text: int = 50 * MIB


class FileKind(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    IMAGE = "image"


_EXTENSION_KIND = {
    ".md": FileKind.DOCUMENT,
    ".markdown": FileKind.DOCUMENT,
    ".txt": FileKind.DOCUMENT,
    ".csv": FileKind.DOCUMENT,
    ".log": FileKind.DOCUMENT,
    ".json": FileKind.DOCUMENT,
    ".pdf": FileKind.DOCUMENT,
    ".epub": FileKind.DOCUMENT,
    ".png": FileKind.IMAGE,
    ".jpg": FileKind.IMAGE,
    ".jpeg": FileKind.IMAGE,
    ".webp": FileKind.IMAGE,
    ".mp3": FileKind.AUDIO,
    ".wav": FileKind.AUDIO,
    ".m4a": FileKind.AUDIO,
    ".aac": FileKind.AUDIO,
    ".flac": FileKind.AUDIO,
    ".ogg": FileKind.AUDIO,
    ".opus": FileKind.AUDIO,
    ".wma": FileKind.AUDIO,
    ".mp4": FileKind.VIDEO,
    ".mov": FileKind.VIDEO,
    ".avi": FileKind.VIDEO,
    ".mkv": FileKind.VIDEO,
    ".webm": FileKind.VIDEO,
    ".mts": FileKind.VIDEO,
    ".ts": FileKind.VIDEO,
    ".flv": FileKind.VIDEO,
}


def max_bytes_for_kind(kind: FileKind) -> int:
    if kind in {FileKind.AUDIO, FileKind.VIDEO}:
        return AUDIO_VIDEO_MAX_BYTES
    if kind is FileKind.IMAGE:
        return IMAGE_MAX_BYTES
    return DOCUMENT_MAX_BYTES


def kind_for_filename(filename: str | None) -> FileKind | None:
    return _EXTENSION_KIND.get(Path(filename or "").suffix.lower())


def stream_upload_to_temp(
    upload: UploadFile,
    *,
    max_bytes: int,
    temp_dir: Path | None = None,
    suffix: str | None = None,
) -> Path:
    """Copy an upload to a temporary file while enforcing actual bytes read."""
    requested_suffix = suffix if suffix is not None else Path(upload.filename or "").suffix
    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=requested_suffix,
        dir=str(temp_dir) if temp_dir is not None else None,
        delete=False,
    )
    path = Path(tmp.name)
    total = 0
    try:
        with tmp:
            while True:
                chunk = upload.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="文件大小超过限制")
                tmp.write(chunk)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _invalid() -> HTTPException:
    return HTTPException(status_code=422, detail="文件内容与扩展名不匹配或文件已损坏")


def _is_ftyp(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp"


def _ftyp_brands(data: bytes) -> set[bytes]:
    if not _is_ftyp(data):
        return set()
    brands = {data[8:12]}
    brands.update(data[index:index + 4] for index in range(16, len(data) - 3, 4))
    return brands


def _is_mp3_frame(data: bytes) -> bool:
    if len(data) < 4:
        return False
    first, second, third = data[:3]
    return (
        first == 0xFF
        and second & 0xE0 == 0xE0
        and (second >> 3) & 0x3 != 0x1
        and (second >> 1) & 0x3 != 0
        and (third >> 4) & 0xF != 0xF
        and (third >> 2) & 0x3 != 0x3
    )


def validate_mp3(path: Path, *, max_id3_tag_bytes: int = MAX_ID3_TAG_BYTES) -> bool:
    """Validate an MP3 frame directly or after a bounded ID3v2 tag."""
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(10)
        if _is_mp3_frame(header):
            return True
        if len(header) < 10 or not header.startswith(b"ID3"):
            return False

        version = header[3]
        if version not in {2, 3, 4}:
            return False
        size_bytes = header[6:10]
        if any(byte & 0x80 for byte in size_bytes):
            return False
        tag_size = sum(byte << shift for byte, shift in zip(size_bytes, (21, 14, 7, 0)))
        if tag_size > max_id3_tag_bytes:
            return False

        footer_size = 10 if version == 4 and header[5] & 0x10 else 0
        frame_offset = 10 + tag_size + footer_size
        if frame_offset + 4 > file_size:
            return False
        handle.seek(frame_offset)
        return _is_mp3_frame(handle.read(4))


def _validate_text(path: Path, suffix: str) -> None:
    data = path.read_bytes()
    if b"\x00" in data:
        raise _invalid()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid() from exc
    if suffix == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise _invalid() from exc


def _invalid_epub(reason: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"无效 EPUB：{reason}")


def validate_epub(path: Path, *, limits: EpubLimits = EpubLimits()) -> None:
    """Validate EPUB ZIP metadata before reading any archive member."""
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > limits.max_entries:
                raise _invalid_epub("文件条目数量超过限制")

            seen: set[str] = set()
            expanded_total = 0
            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                windows_path = PureWindowsPath(name)
                if (
                    not name
                    or "\\" in name
                    or pure.is_absolute()
                    or windows_path.is_absolute()
                    or bool(windows_path.drive)
                    or ".." in pure.parts
                    or name in seen
                ):
                    raise _invalid_epub("包含不安全或重复的文件名")
                seen.add(name)

                if info.flag_bits & 0x1:
                    raise _invalid_epub("不支持加密成员")

                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise _invalid_epub("包含链接或特殊文件")

                if info.file_size > limits.max_member:
                    raise _invalid_epub("单个成员展开后过大")
                expanded_total += info.file_size
                if expanded_total > limits.max_expanded_total:
                    raise _invalid_epub("展开后总大小超过限制")
                if info.file_size:
                    if info.compress_size == 0 or info.file_size > info.compress_size * limits.max_ratio:
                        raise _invalid_epub("压缩比超过限制")

            first = infos[0]
            if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED:
                raise _invalid_epub("mimetype 必须是首个未压缩成员")
            if archive.read(first) != b"application/epub+zip":
                raise _invalid_epub("mimetype 内容不正确")
    except HTTPException:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise _invalid_epub("无法作为安全 ZIP 打开") from exc


def validate_file(path: Path, *, filename: str) -> FileKind:
    """Validate that a supported extension matches the file signature/container."""
    suffix = Path(filename).suffix.lower()
    kind = kind_for_filename(filename)
    if kind is None:
        raise _invalid()

    if suffix in {".txt", ".md", ".markdown", ".csv", ".log", ".json"}:
        _validate_text(path, suffix)
        return kind

    with path.open("rb") as handle:
        head = handle.read(4096)

    valid = False
    if suffix == ".pdf":
        valid = head.startswith(b"%PDF-")
    elif suffix == ".epub":
        valid = head.startswith(b"PK\x03\x04")
        if valid:
            validate_epub(path)
    elif suffix == ".png":
        valid = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif suffix in {".jpg", ".jpeg"}:
        valid = head.startswith(b"\xff\xd8\xff")
    elif suffix == ".webp":
        valid = head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    elif suffix == ".wav":
        valid = head.startswith(b"RIFF") and head[8:12] == b"WAVE"
    elif suffix == ".avi":
        valid = head.startswith(b"RIFF") and head[8:12] == b"AVI "
    elif suffix in {".mp4", ".mov", ".m4a"}:
        brands = _ftyp_brands(head)
        is_quicktime = b"qt  " in brands
        is_m4a = any(brand.startswith((b"M4A", b"M4B", b"M4P")) for brand in brands)
        if suffix == ".mov":
            valid = is_quicktime
        elif suffix == ".m4a":
            valid = is_m4a
        else:
            valid = bool(brands) and not is_quicktime and not is_m4a
    elif suffix == ".mp3":
        valid = validate_mp3(path)
    elif suffix == ".aac":
        valid = len(head) >= 2 and head[0] == 0xFF and head[1] & 0xF6 in {0xF0, 0xF4}
    elif suffix == ".flac":
        valid = head.startswith(b"fLaC")
    elif suffix == ".ogg":
        valid = head.startswith(b"OggS")
    elif suffix == ".opus":
        valid = head.startswith(b"OggS") and b"OpusHead" in head
    elif suffix == ".wma":
        valid = head.startswith(bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c"))
    elif suffix in {".webm", ".mkv"}:
        lower_head = head.lower()
        valid = head.startswith(bytes.fromhex("1a45dfa3")) and (
            (suffix == ".webm" and b"webm" in lower_head and b"matroska" not in lower_head)
            or (suffix == ".mkv" and b"matroska" in lower_head)
        )
    elif suffix in {".ts", ".mts"}:
        valid = len(head) > 188 and head[0] == 0x47 and head[188] == 0x47
    elif suffix == ".flv":
        valid = head.startswith(b"FLV")

    if not valid:
        raise _invalid()
    return kind
