from __future__ import annotations

import io
import json
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException, UploadFile

from zhiji_backend.security.file_intake import (
    CHUNK_SIZE,
    EpubLimits,
    FileKind,
    stream_upload_to_temp,
    validate_epub,
    validate_file,
)


class RecordingStream(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def make_upload(filename: str, data: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(filename=filename, file=RecordingStream(data), headers={"content-type": content_type})


def test_stream_upload_accepts_exact_limit_and_reads_fixed_chunks(tmp_path: Path):
    upload = make_upload("exact.bin", b"a" * 17)

    path = stream_upload_to_temp(upload, max_bytes=17, temp_dir=tmp_path)

    assert path.read_bytes() == b"a" * 17
    assert upload.file.read_sizes == [CHUNK_SIZE, CHUNK_SIZE]


def test_stream_upload_rejects_actual_bytes_over_limit_and_removes_partial(tmp_path: Path):
    upload = make_upload("large.bin", b"a" * 18)

    with pytest.raises(HTTPException) as exc_info:
        stream_upload_to_temp(upload, max_bytes=17, temp_dir=tmp_path)

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "data", "kind"),
    [
        ("doc.pdf", b"%PDF-1.4\n%%EOF\n", FileKind.DOCUMENT),
        ("image.png", b"\x89PNG\r\n\x1a\n" + b"x" * 16, FileKind.IMAGE),
        ("image.jpg", b"\xff\xd8\xff\xe0" + b"x" * 16, FileKind.IMAGE),
        ("image.webp", b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"x" * 8, FileKind.IMAGE),
        ("audio.wav", b"RIFF\x10\x00\x00\x00WAVEfmt " + b"x" * 8, FileKind.AUDIO),
        ("video.avi", b"RIFF\x10\x00\x00\x00AVI LIST" + b"x" * 8, FileKind.VIDEO),
        ("video.mp4", b"\x00\x00\x00\x18ftypisom" + b"x" * 16, FileKind.VIDEO),
        ("video.mov", b"\x00\x00\x00\x18ftypqt  " + b"x" * 16, FileKind.VIDEO),
        ("audio.m4a", b"\x00\x00\x00\x18ftypM4A " + b"x" * 16, FileKind.AUDIO),
        ("audio.mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x64", FileKind.AUDIO),
        ("audio.aac", b"\xff\xf1\x50\x80" + b"x" * 8, FileKind.AUDIO),
        ("audio.flac", b"fLaC" + b"x" * 12, FileKind.AUDIO),
        ("audio.ogg", b"OggS" + b"x" * 24, FileKind.AUDIO),
        ("audio.opus", b"OggS" + b"x" * 20 + b"OpusHead" + b"x" * 8, FileKind.AUDIO),
        ("audio.wma", bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c") + b"x" * 8, FileKind.AUDIO),
        ("video.webm", bytes.fromhex("1a45dfa3") + b"x" * 8 + b"webm" + b"x" * 8, FileKind.VIDEO),
        ("video.mkv", bytes.fromhex("1a45dfa3") + b"x" * 8 + b"matroska" + b"x" * 8, FileKind.VIDEO),
        ("video.ts", b"\x47" + b"x" * 187 + b"\x47" + b"x" * 20, FileKind.VIDEO),
        ("video.mts", b"\x47" + b"x" * 187 + b"\x47" + b"x" * 20, FileKind.VIDEO),
        ("video.flv", b"FLV\x01\x05" + b"x" * 16, FileKind.VIDEO),
    ],
)
def test_validate_file_accepts_supported_signatures(tmp_path: Path, filename: str, data: bytes, kind: FileKind):
    path = tmp_path / filename
    path.write_bytes(data)

    assert validate_file(path, filename=filename) is kind


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("notes.txt", "hello\nworld".encode()),
        ("notes.md", "# hello".encode()),
        ("events.json", json.dumps({"ok": True}).encode()),
        ("data.csv", "a,b\n1,2\n".encode()),
        ("run.log", "started\n".encode()),
    ],
)
def test_validate_file_accepts_utf8_text_and_json(tmp_path: Path, filename: str, data: bytes):
    path = tmp_path / filename
    path.write_bytes(data)

    assert validate_file(path, filename=filename) is FileKind.DOCUMENT


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("fake.pdf", b"not a pdf"),
        ("fake.jpg", b"\x89PNG\r\n\x1a\n" + b"x" * 8),
        ("bad.mp4", b"\x00\x00\x00\x18xxxxisom"),
        ("fake.mp3", b"\xff\xf1\x50\x80" + b"x" * 8),
        ("fake.mov", b"\x00\x00\x00\x18ftypisom" + b"x" * 16),
        ("fake.m4a", b"\x00\x00\x00\x18ftypisom" + b"x" * 16),
        ("fake.webm", bytes.fromhex("1a45dfa3") + b"matroska"),
        ("fake.mkv", bytes.fromhex("1a45dfa3") + b"webm"),
        ("bad.json", b"{not json}"),
        ("bad.txt", b"hello\x00world"),
        ("bad.md", b"\xff\xfe"),
    ],
)
def test_validate_file_rejects_spoofed_or_malformed_input(tmp_path: Path, filename: str, data: bytes):
    path = tmp_path / filename
    path.write_bytes(data)

    with pytest.raises(HTTPException) as exc_info:
        validate_file(path, filename=filename)

    assert exc_info.value.status_code == 422


def write_epub(path: Path, entries: list[tuple[str, bytes, int | None]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            if mode is not None:
                info.create_system = 3
                info.external_attr = mode << 16
            archive.writestr(info, data)


def minimal_epub_entries() -> list[tuple[str, bytes, int | None]]:
    return [
        ("mimetype", b"application/epub+zip", None),
        ("META-INF/container.xml", b"<container/>", None),
        ("OPS/chapter.xhtml", b"<p>Hello</p>", None),
    ]


def test_validate_epub_accepts_minimal_safe_archive(tmp_path: Path):
    path = tmp_path / "book.epub"
    write_epub(path, minimal_epub_entries())

    validate_epub(path)


@pytest.mark.parametrize(
    "entries",
    [
        [("mimetype", b"application/zip", None)],
        minimal_epub_entries() + [("../escape", b"x", None)],
        minimal_epub_entries() + [("/absolute", b"x", None)],
        minimal_epub_entries() + [("C:/absolute", b"x", None)],
        minimal_epub_entries() + [("OPS\\backslash", b"x", None)],
        minimal_epub_entries() + [("OPS/link", b"x", stat.S_IFLNK | 0o777)],
        minimal_epub_entries() + [("OPS/device", b"x", stat.S_IFCHR | 0o600)],
    ],
)
def test_validate_epub_rejects_unsafe_archives(tmp_path: Path, entries):
    path = tmp_path / "unsafe.epub"
    write_epub(path, entries)

    with pytest.raises(HTTPException) as exc_info:
        validate_epub(path)

    assert exc_info.value.status_code == 422


def test_validate_epub_rejects_duplicate_names(tmp_path: Path):
    path = tmp_path / "duplicate.epub"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("OPS/chapter.xhtml", b"one")
            archive.writestr("OPS/chapter.xhtml", b"two")

    with pytest.raises(HTTPException, match="EPUB"):
        validate_epub(path)


def test_validate_epub_rejects_encrypted_member_before_reading(tmp_path: Path):
    info = zipfile.ZipInfo("secret.xhtml")
    info.flag_bits = 0x1
    archive = type("Archive", (), {
        "__enter__": lambda self: self,
        "__exit__": lambda self, *args: None,
        "infolist": lambda self: [info],
        "read": lambda self, member: pytest.fail("encrypted member must not be read"),
    })()

    with patch("zhiji_backend.security.file_intake.zipfile.ZipFile", return_value=archive):
        with pytest.raises(HTTPException, match="加密"):
            validate_epub(tmp_path / "encrypted.epub")


@pytest.mark.parametrize(
    ("limits", "extra_data"),
    [
        (EpubLimits(max_entries=2), b"x"),
        (EpubLimits(max_expanded_total=40), b"x" * 50),
        (EpubLimits(max_member=20), b"x" * 21),
        (EpubLimits(max_ratio=2), b"0" * 1000),
    ],
)
def test_validate_epub_rejects_bombs_with_injected_limits(tmp_path: Path, limits: EpubLimits, extra_data: bytes):
    path = tmp_path / "bomb.epub"
    write_epub(path, minimal_epub_entries() + [("OPS/bomb.bin", extra_data, None)])

    with pytest.raises(HTTPException, match="EPUB"):
        validate_epub(path, limits=limits)
