from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException


def _service() -> ModuleType:
    module_name = "zhiji_backend.brainstorm_concept_service"
    assert importlib.util.find_spec(module_name) is not None, (
        "brainstorm concept service has not been extracted"
    )
    return importlib.import_module(module_name)


def _sql(sql: str) -> str:
    return " ".join(sql.split())


class RecordingConnection:
    def __init__(self, connection: sqlite3.Connection, database: Database) -> None:
        self.connection = connection
        self.database = database

    def execute(self, sql: str, params: object = ()) -> sqlite3.Cursor:
        statement = (_sql(sql), params)
        self.database.statements.append(statement)
        self.database.events.append(("execute", *statement))
        return self.connection.execute(sql, params)


class ConnectionContext(AbstractContextManager[RecordingConnection]):
    def __init__(self, database: Database, number: int) -> None:
        self.database = database
        self.number = number
        connection = sqlite3.connect(database.path)
        connection.row_factory = sqlite3.Row
        self.connection = RecordingConnection(connection, database)

    def __enter__(self) -> RecordingConnection:
        self.database.events.append(("enter", self.number))
        return self.connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        try:
            if exc_type is None:
                self.connection.connection.commit()
            else:
                self.connection.connection.rollback()
        finally:
            self.connection.connection.close()
            self.database.events.append(("exit", self.number))
        return None


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.statements: list[tuple[str, object]] = []
        self.events: list[tuple[object, ...]] = []
        self.connect_count = 0
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE brainstorm_questions (
                    id TEXT PRIMARY KEY,
                    question TEXT,
                    answer TEXT
                );
                CREATE TABLE events (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    content_type TEXT
                );
                CREATE TABLE brainstorm_event_links (
                    question_id TEXT,
                    event_id TEXT,
                    PRIMARY KEY (question_id, event_id)
                );
                """
            )

    def connect(self) -> ConnectionContext:
        self.connect_count += 1
        self.events.append(("connect", self.connect_count))
        return ConnectionContext(self, self.connect_count)

    def seed(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executemany(sql, rows)

    def rows(self, sql: str, params: object = ()) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.path) as connection:
            return connection.execute(sql, params).fetchall()


def _request(
    question_id: str = "question-1",
    name: str = "主概念",
    description: str = "概念描述",
) -> SimpleNamespace:
    return SimpleNamespace(
        question_id=question_id,
        name=name,
        description=description,
    )


def test_list_summary_concepts_preserves_missing_question_error_and_query(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "missing.sqlite")

    with pytest.raises(HTTPException) as raised:
        service.list_summary_concepts("missing", connect_fn=database.connect)

    assert raised.value.status_code == 404
    assert raised.value.detail == "Question not found"
    assert database.statements == [
        (
            "SELECT id, question, answer FROM brainstorm_questions WHERE id = ?",
            ("missing",),
        )
    ]
    assert database.connect_count == 1


def test_list_summary_concepts_preserves_missing_summary_response(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "no-summary.sqlite")
    database.seed(
        "INSERT INTO brainstorm_questions VALUES (?, ?, ?)",
        [("question-1", "问题", None)],
    )

    assert service.list_summary_concepts(
        "question-1", connect_fn=database.connect
    ) == {
        "question_id": "question-1",
        "concepts": [],
        "message": "请先生成总结",
    }
    assert database.connect_count == 1


def test_list_summary_concepts_preserves_regex_deduplication_and_existing_flags(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "concepts.sqlite")
    answer = (
        "开场\n\n"
        "## 概念定义\n\n"
        "### 主概念\n"
        "- **定义**：主概念的定义\n"
        "- **边界**：边界说明\n\n"
        "### 无定义概念\n"
        "补充文字\n\n"
        "### 主概念\n"
        "- **定义**：不应覆盖\n\n"
        "## 相关概念\n\n"
        "- **相关甲**：相关甲说明\n"
        "- **主概念**：重复项\n"
        "- **相关乙**: 多行说明第一行\n第二行\n"
        "## 下一节\n结束"
    )
    database.seed(
        "INSERT INTO brainstorm_questions VALUES (?, ?, ?)",
        [("question-1", "问题", answer)],
    )
    database.seed(
        "INSERT INTO events VALUES (?, ?, ?)",
        [
            ("concept-1", "主概念", "concept"),
            ("article-1", "相关甲", "article"),
            ("concept-2", "相关乙", "concept"),
        ],
    )

    result = service.list_summary_concepts(
        "question-1", connect_fn=database.connect
    )

    assert result == {
        "question_id": "question-1",
        "concepts": [
            {
                "name": "主概念",
                "description": "主概念的定义",
                "precipitated": True,
            },
            {
                "name": "无定义概念",
                "description": "不应覆盖",
                "precipitated": False,
            },
            {
                "name": "相关甲",
                "description": "相关甲说明",
                "precipitated": False,
            },
            {
                "name": "相关乙",
                "description": "多行说明第一行\n第二行",
                "precipitated": True,
            },
        ],
    }
    assert database.statements == [
        (
            "SELECT id, question, answer FROM brainstorm_questions WHERE id = ?",
            ("question-1",),
        ),
        (
            "SELECT title FROM events WHERE content_type = 'concept' AND title IN (?,?,?,?)",
            ["主概念", "无定义概念", "相关甲", "相关乙"],
        ),
    ]
    assert database.connect_count == 2


def test_precipitate_concept_preserves_duplicate_response_and_short_circuit(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "duplicate.sqlite")
    database.seed(
        "INSERT INTO events VALUES (?, ?, ?)",
        [("concept-existing", "主概念", "concept")],
    )

    result = service.precipitate_concept(
        _request(),
        connect_fn=database.connect,
        build_reference_docs_fn=lambda _ids: pytest.fail(
            "reference docs should not be built"
        ),
        create_concept_fn=lambda *_args, **_kwargs: pytest.fail(
            "concept should not be created"
        ),
        logger=logging.getLogger("zhiji_backend.routes.brainstorm_routes"),
    )

    assert result == {
        "status": "exists",
        "event_id": "concept-existing",
        "message": "概念「主概念」已存在",
    }
    assert database.statements == [
        (
            "SELECT id FROM events WHERE content_type = 'concept' AND title = ?",
            ("主概念",),
        )
    ]
    assert database.connect_count == 1


def test_precipitate_concept_preserves_context_create_backlink_and_success(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "create.sqlite")
    database.seed(
        "INSERT INTO brainstorm_event_links VALUES (?, ?)",
        [("question-1", "event-2"), ("question-1", "event-1")],
    )
    create_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def build_reference_docs(
        event_ids: list[str],
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        database.events.append(("build_reference_docs", event_ids))
        assert event_ids == ["event-1", "event-2"]
        return (
            [
                {"title": "文档一", "text": "内容一", "id": "event-1"},
                {"title": "文档二", "text": "内容二", "id": "event-2"},
            ],
            {"event-1": "1", "event-2": "2"},
        )

    def create_concept(*args: object, **kwargs: object) -> dict[str, str]:
        database.events.append(("create_concept", args, kwargs))
        create_calls.append((args, kwargs))
        return {"event_id": "concept-new", "ai_summary": "AI 解释"}

    result = service.precipitate_concept(
        _request(),
        connect_fn=database.connect,
        build_reference_docs_fn=build_reference_docs,
        create_concept_fn=create_concept,
        logger=logging.getLogger("zhiji_backend.routes.brainstorm_routes"),
    )

    assert create_calls == [
        (
            ("主概念", "uncategorized", "概念描述"),
            {
                "force_ai": True,
                "context_docs": [
                    {"title": "文档一", "content": "内容一"},
                    {"title": "文档二", "content": "内容二"},
                ],
            },
        )
    ]
    assert result == {
        "status": "created",
        "event_id": "concept-new",
        "ai_summary": "AI 解释",
    }
    assert database.statements == [
        (
            "SELECT id FROM events WHERE content_type = 'concept' AND title = ?",
            ("主概念",),
        ),
        (
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            ("question-1",),
        ),
        (
            "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
            ("question-1", "concept-new"),
        ),
    ]
    assert database.rows(
        "SELECT question_id, event_id FROM brainstorm_event_links "
        "WHERE event_id = ?",
        ("concept-new",),
    ) == [("question-1", "concept-new")]
    assert database.events == [
        ("connect", 1),
        ("enter", 1),
        (
            "execute",
            "SELECT id FROM events WHERE content_type = 'concept' AND title = ?",
            ("主概念",),
        ),
        ("exit", 1),
        ("connect", 2),
        ("enter", 2),
        (
            "execute",
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            ("question-1",),
        ),
        ("exit", 2),
        ("build_reference_docs", ["event-1", "event-2"]),
        (
            "create_concept",
            ("主概念", "uncategorized", "概念描述"),
            {
                "force_ai": True,
                "context_docs": [
                    {"title": "文档一", "content": "内容一"},
                    {"title": "文档二", "content": "内容二"},
                ],
            },
        ),
        ("connect", 3),
        ("enter", 3),
        (
            "execute",
            "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
            ("question-1", "concept-new"),
        ),
        ("exit", 3),
    ]


def test_precipitate_concept_preserves_empty_context_and_default_ai_summary(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "empty-context.sqlite")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def create_concept(*args: object, **kwargs: object) -> dict[str, str]:
        calls.append((args, kwargs))
        return {"event_id": "concept-new"}

    result = service.precipitate_concept(
        _request(),
        connect_fn=database.connect,
        build_reference_docs_fn=lambda _ids: pytest.fail(
            "reference docs should not be built"
        ),
        create_concept_fn=create_concept,
        logger=logging.getLogger("zhiji_backend.routes.brainstorm_routes"),
    )

    assert calls == [
        (
            ("主概念", "uncategorized", "概念描述"),
            {"force_ai": True, "context_docs": None},
        )
    ]
    assert result == {
        "status": "created",
        "event_id": "concept-new",
        "ai_summary": "",
    }


def test_precipitate_concept_preserves_failure_http_error_and_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service()
    assert service.logger.name == "zhiji_backend.routes.brainstorm_routes"
    database = Database(tmp_path / "failure.sqlite")
    request = _request(name="失败概念")
    historical_logger = logging.getLogger("zhiji_backend.routes.brainstorm_routes")

    def fail_create(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise RuntimeError("模型不可用")

    with caplog.at_level(logging.WARNING, logger=historical_logger.name):
        with pytest.raises(HTTPException) as raised:
            service.precipitate_concept(
                request,
                connect_fn=database.connect,
                build_reference_docs_fn=lambda _ids: pytest.fail(
                    "reference docs should not be built"
                ),
                create_concept_fn=fail_create,
                logger=historical_logger,
            )

    assert raised.value.status_code == 500
    assert raised.value.detail == "沉淀失败: 模型不可用"
    assert caplog.messages == [
        "Concept precipitation failed for 失败概念: 模型不可用"
    ]
    assert database.statements == [
        (
            "SELECT id FROM events WHERE content_type = 'concept' AND title = ?",
            ("失败概念",),
        ),
        (
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            ("question-1",),
        ),
    ]


def test_public_service_signatures_are_keyword_injected() -> None:
    service = _service()
    assert str(inspect.signature(service.list_summary_concepts)) == (
        "(question_id: 'str', *, connect_fn: 'ConnectFn') -> 'dict[str, object]'"
    )
    assert str(inspect.signature(service.precipitate_concept)) == (
        "(req: 'Any', *, connect_fn: 'ConnectFn', "
        "build_reference_docs_fn: 'BuildReferenceDocsFn', "
        "create_concept_fn: 'CreateConceptFn', logger: 'logging.Logger') -> "
        "'dict[str, object]'"
    )
