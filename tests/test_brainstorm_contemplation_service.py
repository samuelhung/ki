from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from zhiji_backend import prompt_registry


def _service() -> ModuleType:
    module_name = "zhiji_backend.brainstorm_contemplation_service"
    assert importlib.util.find_spec(module_name) is not None, (
        "brainstorm contemplation service has not been extracted"
    )
    return importlib.import_module(module_name)


def _sql(sql: str) -> str:
    return " ".join(sql.split())


class RecordingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        statements: list[tuple[str, object]],
    ) -> None:
        self.connection = connection
        self.statements = statements

    def execute(self, sql: str, params: object = ()) -> sqlite3.Cursor:
        self.statements.append((_sql(sql), params))
        return self.connection.execute(sql, params)


class ConnectionContext(AbstractContextManager[RecordingConnection]):
    def __init__(self, database: Database) -> None:
        self.database = database
        connection = sqlite3.connect(database.path)
        connection.row_factory = sqlite3.Row
        self.connection = RecordingConnection(connection, database.statements)

    def __enter__(self) -> RecordingConnection:
        self.database.events.append(("enter", self.database.connect_count))
        return self.connection

    def __exit__(self, *args: object) -> None:
        self.connection.connection.commit()
        self.connection.connection.close()
        self.database.events.append(("exit", self.database.connect_count))
        return None


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.statements: list[tuple[str, object]] = []
        self.events: list[tuple[str, int]] = []
        self.connect_count = 0
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE events (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    ai_summary TEXT,
                    raw_summary TEXT,
                    source_id TEXT,
                    status TEXT,
                    created_at TEXT
                );
                CREATE TABLE brainstorm_questions (
                    id TEXT PRIMARY KEY,
                    question TEXT,
                    topic TEXT,
                    status TEXT,
                    created_at TEXT
                );
                CREATE TABLE brainstorm_event_links (
                    question_id TEXT,
                    event_id TEXT,
                    PRIMARY KEY (question_id, event_id)
                );
                CREATE TABLE brainstorm_contemplate_cache (
                    question_id TEXT,
                    event_id TEXT,
                    relevance TEXT,
                    reason TEXT,
                    PRIMARY KEY (question_id, event_id)
                );
                """
            )

    def connect(self) -> ConnectionContext:
        self.connect_count += 1
        return ConnectionContext(self)

    def seed(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executemany(sql, rows)

    def rows(self, sql: str, params: object = ()) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.path) as connection:
            return connection.execute(sql, params).fetchall()


def _request(direction: str, entity_id: str) -> SimpleNamespace:
    return SimpleNamespace(direction=direction, entity_id=entity_id)


def test_dispatch_preserves_invalid_direction_and_injected_dependencies() -> None:
    service = _service()
    calls: list[tuple[str, str]] = []

    def event_stub(entity_id: str) -> dict[str, object]:
        calls.append(("event", entity_id))
        return {"kind": "event"}

    def question_stub(entity_id: str) -> dict[str, object]:
        calls.append(("question", entity_id))
        return {"kind": "question"}

    dependencies = {
        "contemplate_event_to_questions_fn": event_stub,
        "contemplate_question_to_events_fn": question_stub,
    }
    assert service.contemplate(
        _request("event_to_questions", "event-1"), **dependencies
    ) == {"kind": "event"}
    assert service.contemplate(
        _request("question_to_events", "question-1"), **dependencies
    ) == {"kind": "question"}
    assert service.contemplate(_request("sideways", "entity-1"), **dependencies) == {
        "entity_id": "entity-1",
        "suggestions": [],
        "error": "invalid direction",
    }
    assert calls == [
        ("event", "event-1"),
        ("question", "question-1"),
    ]


def test_get_linked_questions_preserves_exact_query_and_order(tmp_path: Path) -> None:
    service = _service()
    database = Database(tmp_path / "linked.sqlite")
    database.seed(
        "INSERT INTO brainstorm_questions VALUES (?, ?, ?, ?, ?)",
        [
            ("question-old", "old", "认知", "open", "2026-01-01"),
            ("question-new", "new", "财富", "done", "2026-01-03"),
        ],
    )
    database.seed(
        "INSERT INTO brainstorm_event_links VALUES (?, ?)",
        [("question-old", "event-1"), ("question-new", "event-1")],
    )

    result = service.get_linked_questions("event-1", connect_fn=database.connect)

    assert result == {
        "event_id": "event-1",
        "linked_questions": [
            {
                "id": "question-new",
                "question": "new",
                "topic": "财富",
                "created_at": "2026-01-03",
            },
            {
                "id": "question-old",
                "question": "old",
                "topic": "认知",
                "created_at": "2026-01-01",
            },
        ],
    }
    assert database.statements == [
        (
            "SELECT bq.id, bq.question, bq.topic, bq.created_at FROM "
            "brainstorm_event_links bel JOIN brainstorm_questions bq ON bq.id = "
            "bel.question_id WHERE bel.event_id = ? ORDER BY bq.created_at DESC",
            ("event-1",),
        )
    ]


@pytest.mark.parametrize(
    ("event_row", "expected"),
    [
        (None, {"entity_id": "event-1", "suggestions": [], "error": "事件不存在"}),
        (
            ("event-1", "Empty", "   ", "unused", "douyin", "completed", "now"),
            {"entity_id": "event-1", "suggestions": [], "error": "事件没有文本内容"},
        ),
    ],
)
def test_event_to_questions_preserves_missing_and_empty_responses(
    tmp_path: Path,
    event_row: tuple[object, ...] | None,
    expected: dict[str, object],
) -> None:
    service = _service()
    database = Database(tmp_path / "event-empty.sqlite")
    if event_row is not None:
        database.seed("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", [event_row])

    result = service._contemplate_event_to_questions(
        "event-1",
        connect_fn=database.connect,
        call_contemplate_deepseek_fn=lambda _prompt: pytest.fail(
            "AI helper should not be used"
        ),
    )

    assert result == expected
    assert database.statements == [
        (
            "SELECT id, title, ai_summary, raw_summary FROM events WHERE id = ?",
            ("event-1",),
        )
    ]


def test_event_to_questions_preserves_prompt_cache_persistence_and_sorting(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "event-to-questions.sqlite")
    database.seed(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
        [("event-1", "Article", "文" * 3001, "unused", "douyin", "completed", "now")],
    )
    database.seed(
        "INSERT INTO brainstorm_questions VALUES (?, ?, ?, ?, ?)",
        [
            ("q-linked", "linked?", "认知", "open", "2026-01-05"),
            ("q-new-high", "high?", "认知", "open", "2026-01-04"),
            ("q-cached", "cached?", "认知", "open", "2026-01-03"),
            ("q-new-low", "low?", "认知", "open", "2026-01-02"),
            ("q-done", "done?", "认知", "done", "2026-01-06"),
        ],
    )
    database.seed(
        "INSERT INTO brainstorm_event_links VALUES (?, ?)",
        [("q-linked", "event-1")],
    )
    database.seed(
        "INSERT INTO brainstorm_contemplate_cache VALUES (?, ?, ?, ?)",
        [
            ("q-linked", "event-1", "medium", "linked cache"),
            ("q-cached", "event-1", "low", None),
            ("q-done", "event-1", "high", "not open"),
        ],
    )
    calls: list[str] = []

    def call_contemplate_deepseek(prompt: str) -> list[dict[str, object]]:
        calls.append(prompt)
        return [{"index": 0, "relevance": "high", "reason": "direct"}]

    result = service._contemplate_event_to_questions(
        "event-1",
        connect_fn=database.connect,
        call_contemplate_deepseek_fn=call_contemplate_deepseek,
    )

    prompt = (
        "你是一个内容匹配助手。以下是一篇文章，请判断它能回答下面哪些问题。\n"
        "对每个问题，判断是否可以基于文章内容回答：\n"
        "- 如果文章直接涉及该问题的主题，标为 high\n"
        "- 如果文章部分相关或可提供背景，标为 medium\n"
        "- 如果完全无关，标为 low\n"
        "注意：不要因为问题关键词看起来匹配就误判，必须基于文章内容的实质关联。\n"
        "只输出 JSON 数组，不要其他内容。格式：\n"
        '[{"index": 0, "relevance": "high", "reason": "一句话原因"}, ...]\n'
        "只输出 relevance 为 high 或 medium 的项，low 的跳过不输出。\n\n"
        "文章标题：Article\n"
        f"文章内容：\n{'文' * 3000}\n\n"
        "待评估问题：\n[0] high?\n[1] low?"
    )
    assert calls == [prompt]
    assert result == {
        "entity_id": "event-1",
        "entity_title": "Article",
        "suggestions": [
            {
                "question_id": "q-new-high",
                "question_text": "high?",
                "relevance": "high",
                "reason": "direct",
                "link_status": "unlinked",
            },
            {
                "question_id": "q-new-low",
                "question_text": "low?",
                "relevance": "low",
                "reason": "",
                "link_status": "unlinked",
            },
            {
                "question_id": "q-cached",
                "question_text": "cached?",
                "relevance": "low",
                "reason": "",
                "link_status": "unlinked",
            },
            {
                "question_id": "q-linked",
                "question_text": "linked?",
                "relevance": "medium",
                "reason": "linked cache",
                "link_status": "linked",
            },
        ],
    }
    assert database.rows(
        "SELECT question_id, relevance, reason FROM brainstorm_contemplate_cache "
        "WHERE event_id = ? ORDER BY question_id",
        ("event-1",),
    ) == [
        ("q-cached", "low", None),
        ("q-done", "high", "not open"),
        ("q-linked", "medium", "linked cache"),
        ("q-new-high", "high", "direct"),
        ("q-new-low", "low", ""),
    ]
    assert database.connect_count == 5

    database.statements.clear()
    calls.clear()
    cached_result = service._contemplate_event_to_questions(
        "event-1",
        connect_fn=database.connect,
        call_contemplate_deepseek_fn=lambda _prompt: pytest.fail(
            "cached pairs must skip AI helper"
        ),
    )
    assert [item["question_id"] for item in cached_result["suggestions"]] == [
        "q-new-high",
        "q-cached",
        "q-new-low",
        "q-linked",
    ]


@pytest.mark.parametrize(
    ("seed_question", "expected"),
    [
        (False, {"entity_id": "question-1", "suggestions": [], "error": "问题不存在"}),
        (
            True,
            {
                "entity_id": "question-1",
                "entity_title": "why?",
                "suggestions": [],
                "note": "所有内容已关联或已判断",
            },
        ),
    ],
)
def test_question_to_events_preserves_missing_and_no_candidate_responses(
    tmp_path: Path,
    seed_question: bool,
    expected: dict[str, object],
) -> None:
    service = _service()
    database = Database(tmp_path / "question-empty.sqlite")
    if seed_question:
        database.seed(
            "INSERT INTO brainstorm_questions VALUES (?, ?, ?, ?, ?)",
            [("question-1", "why?", "认知", "open", "now")],
        )

    result = service._contemplate_question_to_events(
        "question-1",
        connect_fn=database.connect,
        call_contemplate_deepseek_fn=lambda _prompt: pytest.fail(
            "AI helper should not be used"
        ),
    )

    assert result == expected


def test_question_to_events_preserves_filters_prompt_persistence_and_sorting(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "question-to-events.sqlite")
    database.seed(
        "INSERT INTO brainstorm_questions VALUES (?, ?, ?, ?, ?)",
        [("question-1", "why?", "认知", "open", "now")],
    )
    database.seed(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("event-linked", "Linked", "linked", "", "douyin", "completed", "06"),
            ("event-new-high", "High", "", "高" * 3001, "douyin", "completed", "05"),
            ("event-cached", "Cached", "cached", "", "user-upload", "completed", "04"),
            ("event-new-low", "Low", "low", "", "user-upload", "completed", "03"),
            ("event-rss", "RSS", "rss", "", "bbc-world", "completed", "02"),
            ("event-pending", "Pending", "pending", "", "douyin", "pending", "01"),
        ],
    )
    database.seed(
        "INSERT INTO brainstorm_event_links VALUES (?, ?)",
        [("question-1", "event-linked")],
    )
    database.seed(
        "INSERT INTO brainstorm_contemplate_cache VALUES (?, ?, ?, ?)",
        [("question-1", "event-cached", "medium", None)],
    )
    calls: list[str] = []

    def call_contemplate_deepseek(prompt: str) -> list[dict[str, object]]:
        calls.append(prompt)
        return [{"index": 0, "relevance": "high", "reason": "answers"}]

    result = service._contemplate_question_to_events(
        "question-1",
        connect_fn=database.connect,
        call_contemplate_deepseek_fn=call_contemplate_deepseek,
    )

    prompt = (
        "你是一个内容匹配助手。以下是一个问题，请判断下面哪些文章可以用于回答它。\n"
        "对每篇文章，仔细阅读全文后判断是否可基于其内容回答问题：\n"
        "- 如果文章直接涉及该问题的核心，标为 high\n"
        "- 如果文章部分相关或可提供背景信息，标为 medium\n"
        "- 如果完全无关，标为 low\n"
        "注意：不要因为文章标题或关键词看起来相关就误判，必须基于内容的实质关联。\n"
        '只输出 JSON 数组：[{"index": 0, "relevance": "high", "reason": "一句话原因"}, ...]\n'
        "只输出 high 或 medium，low 跳过。\n\n"
        "问题：why?\n\n"
        f"待评估文章：\n[0] High\n内容：{'高' * 3000}\n\n[1] Low\n内容：low"
    )
    assert calls == [prompt]
    assert result == {
        "entity_id": "question-1",
        "entity_title": "why?",
        "suggestions": [
            {
                "event_id": "event-new-high",
                "event_title": "High",
                "relevance": "high",
                "reason": "answers",
            },
            {
                "event_id": "event-cached",
                "event_title": "Cached",
                "relevance": "medium",
                "reason": "",
            },
        ],
    }
    assert database.rows(
        "SELECT event_id, relevance, reason FROM brainstorm_contemplate_cache "
        "WHERE question_id = ? ORDER BY event_id",
        ("question-1",),
    ) == [
        ("event-cached", "medium", None),
        ("event-new-high", "high", "answers"),
        ("event-new-low", "low", ""),
    ]
    assert database.connect_count == 5

    cached_result = service._contemplate_question_to_events(
        "question-1",
        connect_fn=database.connect,
        call_contemplate_deepseek_fn=lambda _prompt: pytest.fail(
            "cached pairs must skip AI helper"
        ),
    )
    assert [item["event_id"] for item in cached_result["suggestions"]] == [
        "event-new-high",
        "event-cached",
        "event-new-low",
    ]


def test_question_to_events_preserves_closed_connection_stale_cache_behavior(
    tmp_path: Path,
) -> None:
    service = _service()
    database = Database(tmp_path / "stale.sqlite")
    database.seed(
        "INSERT INTO brainstorm_questions VALUES (?, ?, ?, ?, ?)",
        [("question-1", "why?", "认知", "open", "now")],
    )
    database.seed(
        "INSERT INTO brainstorm_contemplate_cache VALUES (?, ?, ?, ?)",
        [("question-1", "deleted-event", "high", "stale")],
    )

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        service._contemplate_question_to_events(
            "question-1",
            connect_fn=database.connect,
            call_contemplate_deepseek_fn=lambda _prompt: pytest.fail(
                "AI helper should not be used"
            ),
        )

    assert database.statements[-1] == (
        "SELECT title, source_id FROM events WHERE id = ?",
        ("deleted-event",),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ('[{"index": 0}]', [{"index": 0}]),
        ('```json\n[{"index": 1}]```', [{"index": 1}]),
        ('[{"index": 2}, {"index":', [{"index": 2}]),
        ("not-json", []),
    ],
)
def test_call_contemplate_deepseek_preserves_json_parsing_and_recovery(
    raw: str | None,
    expected: list[dict[str, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service()
    calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def chat_fn(messages: list[dict[str, str]], **kwargs: object) -> str | None:
        calls.append((messages, kwargs))
        return raw

    with caplog.at_level(
        logging.WARNING, logger="zhiji_backend.routes.brainstorm_routes"
    ):
        result = service._call_contemplate_deepseek(
            "PROMPT", chat_fn=chat_fn, logger=service.logger
        )

    assert result == expected
    assert calls == [
        (
            [
                {
                    "role": "system",
                    "content": "You are a JSON-only API. Always output valid JSON array, nothing else.",
                },
                {"role": "user", "content": "PROMPT"},
            ],
            {
                "temperature": 0.1,
                "max_tokens": 4096,
                "timeout": 120,
                "module": "brainstorm",
                "task": "concept_extract",
            },
        )
    ]
    if raw is not None and raw in {'[{"index": 2}, {"index":', "not-json"}:
        with pytest.raises(json.JSONDecodeError) as error:
            json.loads(raw)
        assert caplog.messages == [
            "Contemplate JSON parse error at line "
            f"{error.value.lineno} col {error.value.colno} — trying partial recovery"
        ]
    else:
        assert caplog.messages == []


def test_contemplate_prompt_registry_moves_ownership_without_digest_or_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    assert prompt_registry.MODULE_MAP["brainstorm"]["contemplate"] == (
        "brainstorm_contemplation_service.py",
        ["_contemplate_question_to_events", "_contemplate_event_to_questions"],
    )
    assert prompt_registry.PROMPT_SOURCES["brainstorm"]["contemplate"] == {
        "prompt": prompt_registry.PromptSource(
            "brainstorm_contemplation_service.py", "_contemplate_event_to_questions"
        )
    }
    prompts = prompt_registry.get_all_prompts()["brainstorm"]["contemplate"]
    payload = json.dumps(
        sorted(prompts.items()), ensure_ascii=False, separators=(",", ":")
    )
    assert tuple(sorted(prompts)) == ("prompt",)
    assert hashlib.sha256(payload.encode()).hexdigest() == (
        "f75a1511dc8c491108bcfb7ca09414238cbecd3094b6672afd026e5bd59d00c3"
    )
    assert service.logger.name == "zhiji_backend.routes.brainstorm_routes"

    original_extract = prompt_registry._extract_prompts_by_function

    def extract_with_leak(filepath: Path) -> dict[str, dict[str, str]]:
        extracted = original_extract(filepath)
        extracted.setdefault("_contemplate_event_to_questions", {})[
            "unrelated_prompt"
        ] = "not public"
        return extracted

    monkeypatch.setattr(
        prompt_registry, "_extract_prompts_by_function", extract_with_leak
    )
    assert (
        "unrelated_prompt"
        not in prompt_registry.get_all_prompts()["brainstorm"]["contemplate"]
    )
