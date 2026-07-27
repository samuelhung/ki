from __future__ import annotations

import importlib
import json
import sqlite3
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


@pytest.fixture
def material_store(tmp_path: Path):
    database = tmp_path / "study.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute(
            """CREATE TABLE study_materials (
                   id TEXT PRIMARY KEY,
                   subject TEXT NOT NULL DEFAULT '',
                   grade TEXT NOT NULL DEFAULT '',
                   textbook TEXT NOT NULL DEFAULT '',
                   study_type TEXT NOT NULL DEFAULT '',
                   title TEXT NOT NULL DEFAULT '',
                   source_type TEXT NOT NULL DEFAULT 'manual',
                   raw_content TEXT NOT NULL DEFAULT '',
                   status TEXT NOT NULL DEFAULT 'draft',
                   score INTEGER,
                   is_correct INTEGER,
                   formats_json TEXT DEFAULT '{}',
                   mistake_tags TEXT DEFAULT '[]',
                   tags_json TEXT DEFAULT '[]',
                   lessons_json TEXT DEFAULT '[]',
                   created_at TEXT DEFAULT (datetime('now')),
                   updated_at TEXT DEFAULT (datetime('now'))
               )"""
        )

    @contextmanager
    def connect_fn():
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    return database, connect_fn


def _textbook_upload(
    service,
    *,
    temp_file: Path,
    study_root: Path,
    resolve_under_fn=resolve_under,
    connect_fn=None,
    init_db_fn=lambda: None,
):
    return service.upload_and_ocr(
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
        resolve_under_fn=resolve_under_fn,
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
        uuid_fn=lambda: "material-1",
        process_pdf_fn=None,
        ocr_page_fn=None,
        study_data_dir=study_root,
        ocr_pdf_max_bytes=50,
        file_kind_type=FileKind,
    )


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

    with pytest.raises(service.PaginationOffsetError):
        service.list_materials(
            "", "", "", 5002, 200, connect_fn=connect_fn, init_db_fn=lambda: None
        )

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

    with pytest.raises(service.InvalidStudyFilePathError):
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
            request_factory=lambda **kwargs: SimpleNamespace(**kwargs),
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


def test_textbook_intake_cleans_temp_and_owned_dirs_when_resolve_fails_before_replace(
    tmp_path: Path,
) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    study_root = tmp_path / "study"
    study_root.mkdir()
    temp_file = tmp_path / "upload.pdf"
    temp_file.write_bytes(b"pdf")

    def fail_raw_verification(root, *parts, **kwargs):
        if parts == ("raw",) and kwargs.get("expected") == "dir":
            raise RuntimeError("resolve failed")
        return resolve_under(root, *parts, **kwargs)

    with pytest.raises(RuntimeError, match="resolve failed"):
        _textbook_upload(
            service,
            temp_file=temp_file,
            study_root=study_root,
            resolve_under_fn=fail_raw_verification,
        )

    assert not temp_file.exists()
    assert not (study_root / "material-1").exists()


def test_textbook_intake_cleans_moved_file_after_init_failure_without_deleting_existing_dir(
    tmp_path: Path,
) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    study_root = tmp_path / "study"
    material_dir = study_root / "material-1"
    material_dir.mkdir(parents=True)
    marker = material_dir / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    temp_file = tmp_path / "upload.pdf"
    temp_file.write_bytes(b"pdf")

    def fail_init():
        raise RuntimeError("init failed")

    with pytest.raises(RuntimeError, match="init failed"):
        _textbook_upload(
            service,
            temp_file=temp_file,
            study_root=study_root,
            init_db_fn=fail_init,
        )

    assert not temp_file.exists()
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (material_dir / "raw").exists()


def test_textbook_intake_never_overwrites_or_deletes_existing_destination(
    tmp_path: Path,
) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    study_root = tmp_path / "study"
    raw_dir = study_root / "material-1/raw"
    raw_dir.mkdir(parents=True)
    existing = raw_dir / "original.pdf"
    existing.write_bytes(b"keep")
    temp_file = tmp_path / "upload.pdf"
    temp_file.write_bytes(b"new")

    with pytest.raises(FileExistsError):
        _textbook_upload(
            service,
            temp_file=temp_file,
            study_root=study_root,
        )

    assert not temp_file.exists()
    assert existing.read_bytes() == b"keep"
    assert raw_dir.exists()


@pytest.mark.parametrize("failure", ["connect", "insert"])
def test_textbook_intake_cleans_moved_file_after_database_failure(
    tmp_path: Path, failure: str
) -> None:
    service = importlib.import_module("zhiji_backend.study_intake_service")
    study_root = tmp_path / "study"
    study_root.mkdir()
    temp_file = tmp_path / "upload.pdf"
    temp_file.write_bytes(b"pdf")

    @contextmanager
    def connect_fn():
        if failure == "connect":
            raise RuntimeError("connect failed")

        class Connection:
            def execute(self, sql, params=()):
                raise RuntimeError("insert failed")

        yield Connection()

    with pytest.raises(RuntimeError, match=f"{failure} failed"):
        _textbook_upload(
            service,
            temp_file=temp_file,
            study_root=study_root,
            connect_fn=connect_fn,
        )

    assert not temp_file.exists()
    assert not (study_root / "material-1").exists()


def test_material_crud_commits_and_preserves_payloads(material_store) -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    database, connect_fn = material_store
    request = SimpleNamespace(
        subject="语文",
        grade="三年级",
        textbook="人教版",
        study_type="阅读",
        title="练习一",
        source_type="manual",
        raw_content="题目正文",
    )

    created = service.create_material(
        request,
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        uuid_fn=lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    assert created == {"material_id": "study-abcdef123456", "status": "draft"}

    detail = service.get_material(
        created["material_id"],
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        json_module=json,
    )
    assert detail["title"] == "练习一"
    assert detail["raw_content"] == "题目正文"
    assert detail["formats_json"] == {}
    assert detail["mistake_tags"] == []

    updated = service.update_material(
        created["material_id"],
        SimpleNamespace(title="已批改", score=88, status=None),
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
    )
    assert updated == {
        "updated": "study-abcdef123456",
        "fields": ["title", "score"],
    }

    listed = service.list_materials(
        "语文",
        "阅读",
        "draft",
        1,
        20,
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
    )
    assert listed["total"] == 1
    assert listed["items"][0]["title"] == "已批改"
    assert listed["items"][0]["score"] == 88

    assert service.delete_material(
        created["material_id"], connect_fn=connect_fn, init_db_fn=lambda: None
    ) == {"deleted": "study-abcdef123456"}
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM study_materials").fetchone()[0] == 0


def test_generate_material_passes_exact_inputs_and_raises_domain_error(
    material_store,
) -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    _, connect_fn = material_store
    with connect_fn() as conn:
        conn.execute(
            """INSERT INTO study_materials
               (id, subject, study_type, raw_content, title)
               VALUES (?, ?, ?, ?, ?)""",
            ("study-1", "数学", "应用题", "题目正文", "练习"),
        )
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return {"material_id": "study-1", "status": "generated"}

    result = service.generate_material(
        "study-1",
        SimpleNamespace(extra_instructions="分步骤"),
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        generate_lecture_notes_fn=generate,
        logger=SimpleNamespace(exception=lambda *args: None),
    )
    assert result == {"material_id": "study-1", "status": "generated"}
    assert calls == [
        {
            "material_id": "study-1",
            "subject": "数学",
            "study_type": "应用题",
            "raw_content": "题目正文",
            "extra_instructions": "分步骤",
        }
    ]

    logged = []
    with pytest.raises(service.MaterialGenerationError, match="model unavailable"):
        service.generate_material(
            "study-1",
            SimpleNamespace(extra_instructions=""),
            connect_fn=connect_fn,
            init_db_fn=lambda: None,
            generate_lecture_notes_fn=lambda **kwargs: (_ for _ in ()).throw(
                RuntimeError("model unavailable")
            ),
            logger=SimpleNamespace(exception=lambda *args: logged.append(args)),
        )
    assert logged == [("生成讲题稿失败: %s", "study-1")]


def test_get_study_file_returns_each_format_and_rejects_invalid_original(
    tmp_path: Path, material_store
) -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    _, connect_fn = material_store
    study_root = tmp_path / "study"
    material_dir = study_root / "study-1"
    raw_dir = material_dir / "raw"
    raw_dir.mkdir(parents=True)
    files = {
        "md": material_dir / "讲题稿版.md",
        "html": material_dir / "讲题稿打印版.html",
        "pdf": material_dir / "讲题稿版.pdf",
        "original": raw_dir / "original.pdf",
    }
    for path in files.values():
        path.write_bytes(b"content")
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO study_materials (id, title, raw_content) VALUES (?, ?, ?)",
            ("study-1", "练习", "study/study-1/raw/original.pdf"),
        )

    for fmt, expected in files.items():
        response = service.get_study_file(
            "study-1",
            fmt,
            connect_fn=connect_fn,
            study_data_dir=study_root,
            resolve_under_fn=resolve_under,
            file_response_type=FileResponse,
            path_security_error_type=PathSecurityError,
            path_type=Path,
        )
        assert Path(response.path) == expected

    with connect_fn() as conn:
        conn.execute(
            "UPDATE study_materials SET raw_content = ? WHERE id = ?",
            ("../outside.pdf", "study-1"),
        )
    with pytest.raises(service.InvalidStudyFilePathError):
        service.get_study_file(
            "study-1",
            "original",
            connect_fn=connect_fn,
            study_data_dir=study_root,
            resolve_under_fn=resolve_under,
            file_response_type=FileResponse,
            path_security_error_type=PathSecurityError,
            path_type=Path,
        )


def test_review_mistake_commits_review_fields(material_store) -> None:
    service = importlib.import_module("zhiji_backend.study_material_service")
    _, connect_fn = material_store
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO study_materials (id, title, raw_content) VALUES (?, ?, ?)",
            ("study-1", "错题", "题目正文"),
        )

    result = service.review_mistake(
        "study-1",
        SimpleNamespace(correct_answer="正确", child_answer="错误"),
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        generate_mistake_review_fn=lambda **kwargs: {
            "score": 72,
            "mistake_tags": ["审题"],
        },
        normalize_review_result_fn=lambda value: {
            **value,
            "status": "reviewed",
            "is_correct": 0,
        },
        json_module=json,
        logger=SimpleNamespace(exception=lambda *args: None),
    )
    assert result["status"] == "reviewed"
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT status, is_correct, score, mistake_tags FROM study_materials WHERE id = ?",
            ("study-1",),
        ).fetchone()
    assert tuple(row) == ("reviewed", 0, 72, '["审题"]')


def test_study_services_do_not_import_fastapi_or_routes() -> None:
    backend = Path(__file__).parents[1] / "src/zhiji_backend"
    for filename in ("study_material_service.py", "study_intake_service.py"):
        source = (backend / filename).read_text(encoding="utf-8")
        assert "from fastapi" not in source
        assert "from .routes" not in source
