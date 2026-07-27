from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from zhiji_backend.security.file_intake import FileKind
from zhiji_backend.security.paths import PathSecurityError, resolve_under


class Cursor:
    def __init__(self, *, row: Any = None, rows: list[Any] | None = None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_material_review_preserves_pipeline_and_transaction_order() -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    trace: list[Any] = []
    connection_index = 0

    class Connection:
        def __init__(self, index: int):
            self.index = index

        def execute(self, sql, params=()):
            trace.append((self.index, " ".join(sql.split()), params))
            if self.index == 0:
                return Cursor(row={"raw_content": "题目"})
            return Cursor()

    @contextmanager
    def connect_fn():
        nonlocal connection_index
        index = connection_index
        connection_index += 1
        trace.append(("enter", index))
        yield Connection(index)
        trace.append(("exit", index))

    result = service.review_mistake(
        "study-1",
        SimpleNamespace(correct_answer="正确", child_answer="错误"),
        connect_fn=connect_fn,
        init_db_fn=lambda: trace.append("init_db"),
        generate_mistake_review_fn=lambda **kwargs: (
            trace.append(("review", kwargs)) or {"score": 72, "mistake_tags": ["审题"]}
        ),
        normalize_review_result_fn=lambda value: {
            **value,
            "status": "reviewed",
            "is_correct": 0,
        },
        json_module=json,
        logger=SimpleNamespace(exception=lambda *args: trace.append(args)),
    )

    assert result["status"] == "reviewed"
    assert trace == [
        "init_db",
        ("enter", 0),
        (
            0,
            "SELECT raw_content FROM study_materials WHERE id = ?",
            ("study-1",),
        ),
        ("exit", 0),
        (
            "review",
            {
                "material_id": "study-1",
                "raw_content": "题目",
                "correct_answer": "正确",
                "child_answer": "错误",
            },
        ),
        ("enter", 1),
        (
            1,
            "UPDATE study_materials SET status = 'reviewed', is_correct = ?, score = COALESCE(?, score), mistake_tags = ?, updated_at = datetime('now') WHERE id = ?",
            (0, 72, '["审题"]', "study-1"),
        ),
        ("exit", 1),
    ]


def test_material_list_rejects_offset_overflow_before_connecting() -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    connected = False

    @contextmanager
    def connect_fn():
        nonlocal connected
        connected = True
        yield None

    with pytest.raises(HTTPException) as exc_info:
        service.list_materials(
            "", "", "", 5002, 200, connect_fn=connect_fn, init_db_fn=lambda: None
        )

    assert exc_info.value.status_code == 422
    assert connected is False


@pytest.mark.parametrize("stored", ["/tmp/secret.pdf", "../secret.pdf", "other/x.pdf"])
def test_material_original_file_rejects_unsafe_database_paths(
    tmp_path: Path, stored: str
) -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    material_dir = tmp_path / "study-1"
    material_dir.mkdir()

    class Connection:
        def execute(self, sql, params=()):
            return Cursor(row={"raw_content": stored})

    @contextmanager
    def connect_fn():
        yield Connection()

    with pytest.raises(HTTPException) as exc_info:
        service.get_study_file(
            "study-1",
            "original",
            connect_fn=connect_fn,
            study_data_dir=tmp_path,
            resolve_under_fn=resolve_under,
            file_response_type=FileResponse,
            path_security_error_type=PathSecurityError,
            path_type=Path,
        )

    assert exc_info.value.status_code == 422


def test_intake_validation_failure_removes_temporary_file(tmp_path: Path) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    temp_file = tmp_path / "upload.pdf"
    temp_file.write_bytes(b"invalid")

    def reject(*args, **kwargs):
        raise HTTPException(status_code=422, detail="invalid")

    with pytest.raises(HTTPException) as exc_info:
        service.upload_and_ocr(
            SimpleNamespace(filename="sheet.pdf"),
            "练习",
            "语文",
            "阅读",
            "三年级",
            "标题",
            kind_for_filename_fn=lambda filename: FileKind.DOCUMENT,
            max_bytes_for_kind_fn=lambda kind: 100,
            stream_upload_to_temp_fn=lambda *args, **kwargs: temp_file,
            validate_file_fn=reject,
            resolve_under_fn=resolve_under,
            connect_fn=None,
            init_db_fn=None,
            uuid_fn=lambda: "unused",
            process_pdf_fn=None,
            ocr_page_fn=None,
            study_data_dir=tmp_path / "study",
            ocr_pdf_max_bytes=50,
            file_kind_type=FileKind,
        )

    assert exc_info.value.status_code == 422
    assert not temp_file.exists()


def test_image_intake_removes_temporary_file_when_ocr_fails(tmp_path: Path) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    temp_file = tmp_path / "upload.jpg"
    temp_file.write_bytes(b"image")

    def fail_ocr(path):
        raise RuntimeError("ocr failed")

    with pytest.raises(RuntimeError, match="ocr failed"):
        service.upload_image(
            SimpleNamespace(filename="page.jpg"),
            "语文",
            "阅读",
            "三年级",
            kind_for_filename_fn=lambda filename: FileKind.IMAGE,
            max_bytes_for_kind_fn=lambda kind: 100,
            stream_upload_to_temp_fn=lambda *args, **kwargs: temp_file,
            validate_file_fn=lambda *args, **kwargs: None,
            ocr_image_fn=fail_ocr,
            create_material_fn=lambda request: pytest.fail("must not create"),
            file_kind_type=FileKind,
        )

    assert not temp_file.exists()


def test_textbook_intake_moves_original_and_preserves_insert_shape(
    tmp_path: Path,
) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    study_root = tmp_path / "study"
    study_root.mkdir()
    temp_file = tmp_path / "upload.pdf"
    temp_file.write_bytes(b"%PDF-1.4\n%%EOF\n")
    executed: list[Any] = []

    class Connection:
        def execute(self, sql, params=()):
            executed.append((" ".join(sql.split()), params))

    @contextmanager
    def connect_fn():
        yield Connection()

    result = service.upload_and_ocr(
        SimpleNamespace(filename="课本.pdf"),
        "教材/课本",
        "语文",
        "阅读",
        "三年级",
        "教材标题",
        kind_for_filename_fn=lambda filename: FileKind.DOCUMENT,
        max_bytes_for_kind_fn=lambda kind: 100,
        stream_upload_to_temp_fn=lambda *args, **kwargs: temp_file,
        validate_file_fn=lambda *args, **kwargs: None,
        resolve_under_fn=resolve_under,
        connect_fn=connect_fn,
        init_db_fn=lambda: executed.append("init_db"),
        uuid_fn=lambda: "material-1",
        process_pdf_fn=None,
        ocr_page_fn=None,
        study_data_dir=study_root,
        ocr_pdf_max_bytes=50,
        file_kind_type=FileKind,
    )

    saved = study_root / "material-1/raw/original.pdf"
    assert saved.exists()
    assert result == {
        "material_id": "material-1",
        "text": "",
        "file_saved": "study/material-1/raw/original.pdf",
        "skip_ocr": True,
        "auto_created": True,
    }
    assert executed[0] == "init_db"
    assert executed[1][1] == (
        "material-1",
        "语文",
        "三年级",
        "教材标题",
        "教材/课本",
        "教材标题",
        "study/material-1/raw/original.pdf",
    )
