from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import pytest

from zhiji_backend import config_manager, db, main
from zhiji_backend.security import redaction

PUBLIC_EXPORTS = {
    db: frozenset(
        {
            "DEFAULT_DB_PATH",
            "DEFAULT_SOURCES",
            "connect",
            "get_db_path",
            "init_db",
            "seed_default_sources",
        }
    ),
    config_manager: frozenset(
        {
            "CONFIG_PATH",
            "DEFAULT_AI_BASE_URL",
            "DEFAULT_AI_MODEL",
            "get_config",
            "get_config_and_credential",
            "get_module_config",
            "load_config",
            "save_config",
            "update_config_and_credential",
        }
    ),
    main: frozenset(
        {
            "ArtifactOpenError",
            "FRONTEND_DIST",
            "INGEST_ROOT",
            "LOG_DIR",
            "PUBLIC_INGEST_ARTIFACTS",
            "PinnedFileResponse",
            "ProtectedPathMiddleware",
            "RELEASES_DIR",
            "TrustedHostMiddleware",
            "ZHIJI_HOME",
            "api_auth",
            "app",
            "ensure_migrations",
            "get_db_path",
            "init_db",
            "lifespan",
            "load_config",
            "open_regular_under",
            "retired_digest_endpoint",
            "safe_identifier",
            "seed_default_sources",
            "serve_ingest_artifact",
            "serve_release",
            "spa_fallback",
            "start_usage_writer",
            "start_worker",
            "stop_usage_writer",
            "stop_worker",
        }
    ),
    redaction: frozenset(
        {
            "MAX_REDACTED_TEXT_LENGTH",
            "MAX_REDACTION_INPUT_LENGTH",
            "MAX_TASK_ERROR_LENGTH",
            "REDACTED",
            "RedactingFormatter",
            "SecureTimedRotatingFileHandler",
            "classify_task_error",
            "redact_text",
            "sanitize_task_error",
        }
    ),
}

PUBLIC_SIGNATURES = {
    db: {
        "get_db_path": "() -> 'Path'",
        "connect": "(*, busy_timeout_ms: 'int' = 5000) -> 'Iterator[sqlite3.Connection]'",
        "init_db": "() -> 'None'",
        "seed_default_sources": "() -> 'int'",
    },
    config_manager: {
        "load_config": "(*, persist_normalization: 'bool' = True) -> 'dict[str, Any]'",
        "get_config": "() -> 'dict[str, Any]'",
        "get_config_and_credential": "() -> 'tuple[dict[str, Any], str]'",
        "save_config": "(config: 'dict | None' = None) -> 'None'",
        "update_config_and_credential": (
            "(config: 'dict', requested_api_key: 'str | None') -> 'None'"
        ),
        "get_module_config": "(module: 'str', task: 'str') -> 'dict'",
    },
    main: {
        "lifespan": "(app: 'FastAPI')",
        "TrustedHostMiddleware": (
            "(app: 'ASGIApp', allowed_hosts: 'Sequence[str] | None' = None, "
            "www_redirect: 'bool' = True) -> 'None'"
        ),
        "ProtectedPathMiddleware": (
            "(app: 'ASGIApp', dispatch: 'DispatchFunction | None' = None) -> 'None'"
        ),
        "api_auth": "(request: 'Request', call_next)",
        "spa_fallback": "(request: 'Request', call_next)",
        "retired_digest_endpoint": "()",
        "serve_ingest_artifact": "(kind: 'str', filename: 'str')",
        "serve_release": "(filename: 'str')",
        "ensure_migrations": "(db_path: 'Path') -> 'None'",
        "get_db_path": "() -> 'Path'",
        "load_config": "(*, persist_normalization: 'bool' = True) -> 'dict[str, Any]'",
        "init_db": "() -> 'None'",
        "seed_default_sources": "() -> 'int'",
        "start_usage_writer": "() -> 'bool'",
        "stop_usage_writer": "(timeout: 'float' = 5.0) -> 'int'",
        "start_worker": "() -> 'None'",
        "stop_worker": "() -> 'bool'",
        "open_regular_under": (
            "(root: 'os.PathLike[str] | str', "
            "*parts: 'os.PathLike[str] | str') -> 'OpenedArtifact'"
        ),
        "safe_identifier": "(value: 'str') -> 'str'",
        "PinnedFileResponse": "(opened: 'OpenedArtifact', *, filename: 'str') -> 'None'",
    },
    redaction: {
        "redact_text": "(value: 'Any') -> 'str'",
        "RedactingFormatter": (
            "(fmt=None, datefmt=None, style='%', validate=True, *, defaults=None)"
        ),
        "SecureTimedRotatingFileHandler": (
            "(filename: 'str | os.PathLike[str]', *args, **kwargs)"
        ),
        "classify_task_error": "(error: 'BaseException | str | None') -> 'str'",
        "sanitize_task_error": "(error: 'BaseException | str | None') -> 'str'",
    },
}

EXPECTED_ROUTE_ORDER = [
    ("Route", "/openapi.json", ("GET", "HEAD"), "openapi"),
    ("Route", "/docs", ("GET", "HEAD"), "swagger_ui_html"),
    ("Route", "/docs/oauth2-redirect", ("GET", "HEAD"), "swagger_ui_redirect"),
    ("Route", "/redoc", ("GET", "HEAD"), "redoc_html"),
    ("IncludedRouter", "dashboard_router"),
    ("IncludedRouter", "source_router"),
    ("IncludedRouter", "event_router"),
    ("IncludedRouter", "translate_router"),
    ("IncludedRouter", "brainstorm_router"),
    ("IncludedRouter", "briefing_router"),
    ("IncludedRouter", "ingest_router"),
    ("IncludedRouter", "series_router"),
    ("IncludedRouter", "config_router"),
    ("IncludedRouter", "task_router"),
    ("IncludedRouter", "usage_router"),
    ("IncludedRouter", "log_router"),
    ("IncludedRouter", "system_router"),
    ("IncludedRouter", "prompt_router"),
    ("IncludedRouter", "study_router"),
    ("IncludedRouter", "chain_router"),
    ("APIRoute", "/api/digest/generate", ("POST",), "retired_digest_endpoint"),
    ("APIRoute", "/api/digest/latest", ("GET",), "retired_digest_endpoint"),
    (
        "APIRoute",
        "/ingest/{kind}/{filename:path}",
        ("GET", "HEAD"),
        "serve_ingest_artifact",
    ),
    ("APIRoute", "/releases/{filename:path}", ("GET", "HEAD"), "serve_release"),
]

EXPECTED_OPENAPI_OPERATIONS = [
    ("/api/health", "get", "health_api_health_get"),
    ("/api/system/health", "get", "system_health_api_system_health_get"),
    ("/api/ingest/stats", "get", "ingest_stats_api_ingest_stats_get"),
    ("/api/dashboard/summary", "get", "dashboard_summary_api_dashboard_summary_get"),
    ("/api/dashboard/trend", "get", "dashboard_trend_api_dashboard_trend_get"),
    ("/api/sources", "get", "list_sources_api_sources_get"),
    ("/api/sources/{source_id}/toggle", "put", "toggle_source_api_sources__source_id__toggle_put"),
    ("/api/sources/{source_id}/collect", "post", "collect_source_api_sources__source_id__collect_post"),
    ("/api/events", "get", "list_events_api_events_get"),
    ("/api/events/topic-counts", "get", "event_topic_counts_api_events_topic_counts_get"),
    ("/api/events/{event_id}", "get", "get_event_api_events__event_id__get"),
    ("/api/events/{event_id}", "delete", "delete_event_api_events__event_id__delete"),
    ("/api/events/batch-delete", "post", "batch_delete_events_api_events_batch_delete_post"),
    ("/api/events/{event_id}/summarize", "post", "summarize_event_api_events__event_id__summarize_post"),
    ("/api/collect", "post", "collect_api_collect_post"),
    ("/api/events/{event_id}/tag", "post", "tag_single_event_api_events__event_id__tag_post"),
    ("/api/tag/batch", "post", "tag_batch_api_tag_batch_post"),
    ("/api/events/{event_id}/similar", "get", "similar_events_api_events__event_id__similar_get"),
    ("/api/classify/batch", "post", "batch_classify_api_classify_batch_post"),
    ("/api/classify/event/{event_id}", "post", "classify_single_api_classify_event__event_id__post"),
    ("/api/translate/run", "post", "run_translation_api_translate_run_post"),
    ("/api/translate/backfill", "post", "backfill_translation_api_translate_backfill_post"),
    ("/api/brainstorm", "get", "list_brainstorm_questions_api_brainstorm_get"),
    ("/api/brainstorm", "post", "create_brainstorm_question_api_brainstorm_post"),
    ("/api/brainstorm/topic-counts", "get", "brainstorm_topic_counts_api_brainstorm_topic_counts_get"),
    ("/api/brainstorm/{question_id}", "get", "get_brainstorm_question_api_brainstorm__question_id__get"),
    ("/api/brainstorm/{question_id}", "delete", "delete_brainstorm_question_api_brainstorm__question_id__delete"),
    ("/api/brainstorm/batch-delete", "post", "batch_delete_brainstorm_questions_api_brainstorm_batch_delete_post"),
    ("/api/brainstorm/{question_id}/done", "post", "mark_brainstorm_done_api_brainstorm__question_id__done_post"),
    ("/api/brainstorm/answer", "post", "get_answer_for_question_api_brainstorm_answer_post"),
    ("/api/brainstorm/{question_id}/conversation/start", "post", "start_conversation_api_brainstorm__question_id__conversation_start_post"),
    ("/api/brainstorm/{question_id}/conversation/message", "post", "send_conversation_message_api_brainstorm__question_id__conversation_message_post"),
    ("/api/brainstorm/{question_id}/conversation", "get", "get_conversation_api_brainstorm__question_id__conversation_get"),
    ("/api/brainstorm/{question_id}/conversation/summary", "post", "generate_conversation_summary_api_brainstorm__question_id__conversation_summary_post"),
    ("/api/brainstorm/contemplate", "post", "contemplate_api_brainstorm_contemplate_post"),
    ("/api/brainstorm/event/{event_id}/linked-questions", "get", "get_linked_questions_api_brainstorm_event__event_id__linked_questions_get"),
    ("/api/brainstorm/{question_id}/concepts", "get", "list_summary_concepts_api_brainstorm__question_id__concepts_get"),
    ("/api/brainstorm/concepts/precipitate", "post", "precipitate_concept_api_brainstorm_concepts_precipitate_post"),
    ("/api/briefing/generate", "post", "generate_news_briefing_api_briefing_generate_post"),
    ("/api/briefing/latest", "get", "get_latest_briefing_api_briefing_latest_get"),
    ("/api/briefing", "get", "get_briefing_history_api_briefing_get"),
    ("/api/briefing/{briefing_id}", "get", "get_briefing_detail_api_briefing__briefing_id__get"),
    ("/api/ingest/douyin", "post", "ingest_douyin_api_ingest_douyin_post"),
    ("/api/ingest/concept", "post", "ingest_concept_api_ingest_concept_post"),
    ("/api/ingest/file", "post", "ingest_file_api_ingest_file_post"),
    ("/api/ingest/queue", "get", "ingest_queue_api_ingest_queue_get"),
    ("/api/ingest/status/{event_id}", "get", "ingest_status_api_ingest_status__event_id__get"),
    ("/api/ingest/clear-old", "delete", "clear_old_ingest_api_ingest_clear_old_delete"),
    ("/api/ingest/queue/{task_id}", "delete", "delete_queue_task_api_ingest_queue__task_id__delete"),
    ("/api/ingest/queue/{task_id}/retry", "post", "retry_queue_task_api_ingest_queue__task_id__retry_post"),
    ("/api/ingest/series", "get", "list_series_api_ingest_series_get"),
    ("/api/ingest/series", "post", "create_series_api_ingest_series_post"),
    ("/api/ingest/series/candidates", "get", "list_candidates_api_ingest_series_candidates_get"),
    ("/api/ingest/series/discover", "post", "discover_series_api_ingest_series_discover_post"),
    ("/api/ingest/series/discover/stage1", "post", "discover_stage1_api_ingest_series_discover_stage1_post"),
    ("/api/ingest/series/discover/stage2", "post", "discover_stage2_api_ingest_series_discover_stage2_post"),
    ("/api/ingest/series/discover/by-topic", "post", "discover_by_topic_api_ingest_series_discover_by_topic_post"),
    ("/api/ingest/series/{series_id}/expand", "post", "expand_series_api_ingest_series__series_id__expand_post"),
    ("/api/ingest/series/suggest-name", "post", "suggest_series_name_api_ingest_series_suggest_name_post"),
    ("/api/ingest/series/{series_id}", "delete", "delete_series_api_ingest_series__series_id__delete"),
    ("/api/ingest/series/{series_id}", "put", "update_series_api_ingest_series__series_id__put"),
    ("/api/ingest/series/{series_id}", "get", "get_series_detail_api_ingest_series__series_id__get"),
    ("/api/ingest/series/merge", "post", "merge_series_api_ingest_series_merge_post"),
    ("/api/ingest/series/{series_id}/intro", "put", "generate_series_intro_api_ingest_series__series_id__intro_put"),
    ("/api/ingest/series/{series_id}/summary", "put", "generate_series_summary_api_ingest_series__series_id__summary_put"),
    ("/api/ingest/series/{series_id}/paper", "put", "generate_series_paper_api_ingest_series__series_id__paper_put"),
    ("/api/ingest/series/{series_id}/sort", "put", "reorder_series_api_ingest_series__series_id__sort_put"),
    ("/api/ingest/series/{series_id}/suggestions", "get", "get_series_suggestions_api_ingest_series__series_id__suggestions_get"),
    ("/api/ingest/series/{series_id}/members", "post", "add_series_members_api_ingest_series__series_id__members_post"),
    ("/api/system-config", "get", "read_config_api_system_config_get"),
    ("/api/system-config", "put", "write_config_api_system_config_put"),
    ("/api/tasks", "get", "list_tasks_api_tasks_get"),
    ("/api/tasks", "post", "create_task_api_tasks_post"),
    ("/api/tasks/due", "get", "list_tasks_due_range_api_tasks_due_get"),
    ("/api/tasks/stats", "get", "get_task_stats_api_tasks_stats_get"),
    ("/api/tasks/{task_id}", "get", "get_task_api_tasks__task_id__get"),
    ("/api/tasks/{task_id}", "put", "update_task_api_tasks__task_id__put"),
    ("/api/tasks/{task_id}", "delete", "delete_task_api_tasks__task_id__delete"),
    ("/api/tasks/{task_id}/judge", "post", "judge_task_api_tasks__task_id__judge_post"),
    ("/api/usage/dashboard", "get", "dashboard_api_usage_dashboard_get"),
    ("/api/logs", "get", "get_logs_api_logs_get"),
    ("/api/system/database", "get", "database_info_api_system_database_get"),
    ("/api/system/prompts", "get", "list_prompts_api_system_prompts_get"),
    ("/api/study/list", "get", "list_materials_api_study_list_get"),
    ("/api/study/{material_id}", "get", "get_material_api_study__material_id__get"),
    ("/api/study/{material_id}", "put", "update_material_api_study__material_id__put"),
    ("/api/study/{material_id}", "delete", "delete_material_api_study__material_id__delete"),
    ("/api/study/create", "post", "create_material_api_study_create_post"),
    ("/api/study/upload", "post", "upload_and_ocr_api_study_upload_post"),
    ("/api/study/{material_id}/generate", "post", "generate_material_api_study__material_id__generate_post"),
    ("/api/study/{material_id}/review", "post", "review_mistake_api_study__material_id__review_post"),
    ("/api/study/{material_id}/file/{fmt}", "get", "get_study_file_api_study__material_id__file__fmt__get"),
    ("/api/study/upload-image", "post", "upload_image_api_study_upload_image_post"),
    ("/api/study/mistakes/list", "get", "list_mistakes_api_study_mistakes_list_get"),
    ("/api/study/stats", "get", "get_stats_api_study_stats_get"),
    ("/api/chains", "get", "list_chains_api_chains_get"),
    ("/api/chains/meta", "get", "list_chain_meta_api_chains_meta_get"),
    ("/api/chains/flow-summary", "post", "save_flow_summary_api_chains_flow_summary_post"),
    ("/api/chains/nodes", "get", "list_nodes_api_chains_nodes_get"),
    ("/api/chains/nodes", "post", "create_node_api_chains_nodes_post"),
    ("/api/chains/analyze", "post", "analyze_chain_impact_api_chains_analyze_post"),
    ("/api/chains/report", "post", "chain_report_api_chains_report_post"),
    ("/api/chains/nodes/{node_id}", "put", "update_node_api_chains_nodes__node_id__put"),
    ("/api/chains/nodes/{node_id}", "delete", "delete_node_api_chains_nodes__node_id__delete"),
    ("/api/chains/nodes/ai-update", "post", "ai_update_node_api_chains_nodes_ai_update_post"),
    ("/api/chains/nodes/ai-collect", "post", "ai_collect_node_data_api_chains_nodes_ai_collect_post"),
    ("/api/chains/ai-collect-all", "post", "ai_collect_chain_all_api_chains_ai_collect_all_post"),
    ("/api/chains/hints", "get", "list_hints_api_chains_hints_get"),
    ("/api/chains/hints/count", "get", "count_hints_api_chains_hints_count_get"),
    ("/api/chains/hints/{hint_id}/resolve", "post", "resolve_hint_api_chains_hints__hint_id__resolve_post"),
    ("/api/chains/suggestions", "get", "list_suggestions_api_chains_suggestions_get"),
    ("/api/chains/suggestions/count", "get", "count_suggestions_api_chains_suggestions_count_get"),
    ("/api/chains/suggestions/{sid}/adopt", "post", "adopt_suggestion_api_chains_suggestions__sid__adopt_post"),
    ("/api/chains/suggestions/{sid}/dismiss", "post", "dismiss_suggestion_api_chains_suggestions__sid__dismiss_post"),
    ("/api/chains/hints/sync", "post", "sync_extracted_hints_api_chains_hints_sync_post"),
    ("/api/chains/chat", "post", "chain_chat_api_chains_chat_post"),
    ("/api/chains/overlap-check", "get", "check_chain_overlaps_api_chains_overlap_check_get"),
    ("/api/chains/merge", "post", "merge_chains_api_chains_merge_post"),
    ("/ingest/{kind}/{filename}", "get", "serve_ingest_artifact_ingest__kind___filename__get"),
    ("/ingest/{kind}/{filename}", "head", "serve_ingest_artifact_ingest__kind___filename__get"),
    ("/releases/{filename}", "get", "serve_release_releases__filename__get"),
    ("/releases/{filename}", "head", "serve_release_releases__filename__get"),
]


def _planned_module(name: str) -> Any:
    module_name = f"zhiji_backend.{name}"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"{module_name} has not been extracted")


def test_platform_public_exports_and_signatures_are_stable() -> None:
    for module, expected_exports in PUBLIC_EXPORTS.items():
        missing = expected_exports.difference(vars(module))
        assert not missing, f"{module.__name__} missing public exports: {sorted(missing)}"
        assert set(PUBLIC_SIGNATURES[module]).issubset(expected_exports)

    for module, expected in PUBLIC_SIGNATURES.items():
        for name, signature in expected.items():
            exported = getattr(module, name)
            assert callable(exported), f"{module.__name__}.{name} is not callable"
            assert str(inspect.signature(exported)) == signature

    assert config_manager.DEFAULT_AI_MODEL == "deepseek-v4-pro-max"
    assert config_manager.DEFAULT_AI_BASE_URL == "http://10.8.0.13:3000/v1"
    assert main.PUBLIC_INGEST_ARTIFACTS == frozenset(
        {"videos", "audio", "documents", "transcripts", "summaries"}
    )
    assert main.app.title == "知几"
    assert redaction.REDACTED == "[REDACTED]"
    assert redaction.MAX_REDACTION_INPUT_LENGTH == 65_536
    assert redaction.MAX_REDACTED_TEXT_LENGTH == 16_384
    assert redaction.MAX_TASK_ERROR_LENGTH == 200


def test_database_connection_pragmas_and_row_factory_are_stable(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "platform.sqlite"))

    connection = db._open_connection(busy_timeout_ms=-10)
    try:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        connection.close()


@pytest.mark.parametrize("raises", [False, True], ids=["commit", "rollback"])
def test_database_transaction_commits_or_rolls_back_and_always_closes(
    monkeypatch, raises
) -> None:
    calls: list[str] = []

    class ConnectionSpy:
        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

        def close(self) -> None:
            calls.append("close")

    connection = ConnectionSpy()
    monkeypatch.setattr(db, "_open_connection", lambda **_kwargs: connection)

    if raises:
        with pytest.raises(RuntimeError, match="transaction failed"):
            with db.connect() as yielded:
                assert yielded is connection
                raise RuntimeError("transaction failed")
        assert calls == ["rollback", "close"]
    else:
        with db.connect() as yielded:
            assert yielded is connection
        assert calls == ["commit", "close"]


def test_database_schema_and_migration_order_is_stable(monkeypatch) -> None:
    calls: list[str] = []

    class ConnectionSpy:
        def executescript(self, sql: str) -> None:
            calls.append("schema" if "CREATE TABLE IF NOT EXISTS sources" in sql else "indexes")

        def execute(self, sql: str, *_args) -> Any:
            if sql == "PRAGMA table_info(brainstorm_questions)":
                calls.append("_migrate_brainstorm")

                class CursorSpy:
                    @staticmethod
                    def fetchall() -> list[Any]:
                        return []

                return CursorSpy()
            return None

    @contextmanager
    def fake_connect(**_kwargs):
        yield ConnectionSpy()

    migration_names = (
        "_migrate_events_cn",
        "_migrate_series",
        "_migrate_ingest_tasks_retry",
        "_migrate_video_md5",
        "_migrate_textbook",
        "_migrate_lessons_json",
        "_migrate_chain_reports",
        "_migrate_chain_meta",
        "_backfill_fts",
    )
    monkeypatch.setattr(db, "connect", fake_connect)
    for name in migration_names:
        monkeypatch.setattr(db, name, lambda _conn, name=name: calls.append(name))
    monkeypatch.setattr(
        db,
        "_migrate_brainstorm_answers_to_messages",
        lambda _conn: calls.append("_migrate_brainstorm_answers_to_messages"),
    )

    db.init_db()

    assert calls == [
        "schema",
        "_migrate_events_cn",
        "_migrate_brainstorm",
        "_migrate_brainstorm_answers_to_messages",
        *migration_names[1:4],
        "indexes",
        *migration_names[4:],
    ]


def test_default_source_seed_count_and_idempotence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "seed.sqlite"))

    assert len(db.DEFAULT_SOURCES) == 8
    assert db.seed_default_sources() == 8
    assert db.seed_default_sources() == 0
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 8


def test_fastapi_route_order_and_openapi_operation_ids_are_stable() -> None:
    router_names = {
        id(getattr(main, name)): name
        for name in (
            "dashboard_router",
            "source_router",
            "event_router",
            "translate_router",
            "brainstorm_router",
            "briefing_router",
            "ingest_router",
            "series_router",
            "config_router",
            "task_router",
            "usage_router",
            "log_router",
            "system_router",
            "prompt_router",
            "study_router",
            "chain_router",
        )
    }
    route_snapshot = []
    for route in main.app.routes:
        if type(route).__name__ == "_IncludedRouter":
            route_snapshot.append(
                (
                    "IncludedRouter",
                    router_names.get(id(route.original_router), "<unknown-router>"),
                )
            )
        else:
            route_snapshot.append(
                (
                    type(route).__name__,
                    getattr(route, "path", None),
                    tuple(sorted(getattr(route, "methods", ()) or ())),
                    getattr(route, "name", None),
                )
            )
    assert route_snapshot == EXPECTED_ROUTE_ORDER

    snapshot_script = """
import json
from zhiji_backend.main import app
paths = app.openapi()["paths"]
print(json.dumps([
    (path, method, operation["operationId"])
    for path, path_item in paths.items()
    for method, operation in path_item.items()
]))
"""
    environment = dict(os.environ, PYTHONHASHSEED="0")
    completed = subprocess.run(
        [sys.executable, "-c", snapshot_script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    operation_snapshot = [tuple(item) for item in json.loads(completed.stdout)]
    assert operation_snapshot == EXPECTED_OPENAPI_OPERATIONS


@pytest.mark.parametrize(
    "first_module_name",
    ["db_schema", "db_migrations"],
    ids=["db-schema", "db-migrations"],
)
def test_db_platform_forwarding_contract(first_module_name, monkeypatch) -> None:
    first_module = _planned_module(first_module_name)
    other_module_name = (
        "db_migrations" if first_module_name == "db_schema" else "db_schema"
    )
    other_module = _planned_module(other_module_name)
    modules = {
        first_module_name: first_module,
        other_module_name: other_module,
    }
    connection = object()
    calls: list[tuple[str, object]] = []

    @contextmanager
    def fake_connect(**_kwargs):
        yield connection

    monkeypatch.setattr(db, "connect", fake_connect)
    monkeypatch.setattr(
        modules["db_schema"],
        "create_schema",
        lambda received: calls.append(("create_schema", received)),
    )
    monkeypatch.setattr(
        modules["db_migrations"],
        "run_migrations",
        lambda received: calls.append(("run_migrations", received)),
    )

    db.init_db()

    assert calls == [
        ("create_schema", connection),
        ("run_migrations", connection),
    ]


def test_config_persistence_forwarding_contract() -> None:
    module = _planned_module("config_persistence")
    expected = {
        "_write_config": "write_config",
        "_snapshot_config_file": "snapshot_config_file",
        "_config_file_matches": "config_file_matches",
        "_restore_config_file": "restore_config_file",
    }
    for facade_name, extracted_name in expected.items():
        assert getattr(config_manager, facade_name) is getattr(module, extracted_name)


def test_log_handler_forwarding_contract() -> None:
    module = _planned_module("security.log_handlers")
    assert redaction.SecureTimedRotatingFileHandler is module.SecureTimedRotatingFileHandler


def test_app_lifecycle_forwarding_contract(monkeypatch) -> None:
    module = _planned_module("app_lifecycle")
    captured: dict[str, Any] = {}
    app_sentinel = object()
    yielded_sentinel = object()
    dependencies = {
        "ensure_migrations": object(),
        "get_db_path": object(),
        "load_config": object(),
        "init_db": object(),
        "seed_default_sources": object(),
        "start_usage_writer": object(),
        "stop_usage_writer": object(),
        "start_worker": object(),
        "stop_worker": object(),
    }
    logger_sentinel = object()

    @asynccontextmanager
    async def extracted_lifespan(app, **kwargs):
        captured.update({"app": app, **kwargs})
        yield yielded_sentinel

    monkeypatch.setattr(module, "lifespan", extracted_lifespan)
    for name, dependency in dependencies.items():
        monkeypatch.setattr(main, name, dependency)
    monkeypatch.setattr(main.logging, "getLogger", lambda name: logger_sentinel)

    async def exercise() -> None:
        async with main.lifespan(app_sentinel) as yielded:
            assert yielded is yielded_sentinel

    asyncio.run(exercise())

    assert captured == {
        "app": app_sentinel,
        "logger": logger_sentinel,
        **dependencies,
    }


def test_api_middleware_forwarding_contract() -> None:
    module = _planned_module("api_middleware")
    for name in (
        "TrustedHostMiddleware",
        "ProtectedPathMiddleware",
        "api_auth",
        "spa_fallback",
    ):
        assert getattr(main, name) is getattr(module, name)


def test_static_delivery_forwarding_contract(monkeypatch) -> None:
    module = _planned_module("static_delivery")
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    result_sentinel = object()
    dependencies = {
        "PUBLIC_INGEST_ARTIFACTS": object(),
        "INGEST_ROOT": object(),
        "RELEASES_DIR": object(),
        "safe_identifier": object(),
        "open_regular_under": object(),
        "PinnedFileResponse": object(),
        "ArtifactOpenError": object(),
        "HTTPException": object(),
        "JSONResponse": object(),
        "Path": object(),
    }

    async def record(name: str, *args, **kwargs):
        calls.append((name, args, kwargs))
        return result_sentinel

    monkeypatch.setattr(
        module,
        "retired_digest_endpoint",
        lambda **kwargs: record("retired_digest_endpoint", **kwargs),
    )
    monkeypatch.setattr(
        module,
        "serve_ingest_artifact",
        lambda *args, **kwargs: record("serve_ingest_artifact", *args, **kwargs),
    )
    monkeypatch.setattr(
        module,
        "serve_release",
        lambda *args, **kwargs: record("serve_release", *args, **kwargs),
    )
    for name, dependency in dependencies.items():
        monkeypatch.setattr(main, name, dependency)

    async def exercise() -> None:
        assert await main.retired_digest_endpoint() is result_sentinel
        assert await main.serve_ingest_artifact("videos", "event.mp4") is result_sentinel
        assert await main.serve_release("zhiji.dmg") is result_sentinel

    asyncio.run(exercise())

    assert calls == [
        (
            "retired_digest_endpoint",
            (),
            {"json_response": dependencies["JSONResponse"]},
        ),
        (
            "serve_ingest_artifact",
            ("videos", "event.mp4"),
            {
                "public_ingest_artifacts": dependencies["PUBLIC_INGEST_ARTIFACTS"],
                "ingest_root": dependencies["INGEST_ROOT"],
                "safe_identifier": dependencies["safe_identifier"],
                "open_regular_under": dependencies["open_regular_under"],
                "pinned_file_response": dependencies["PinnedFileResponse"],
                "artifact_open_error": dependencies["ArtifactOpenError"],
                "http_exception": dependencies["HTTPException"],
            },
        ),
        (
            "serve_release",
            ("zhiji.dmg",),
            {
                "releases_dir": dependencies["RELEASES_DIR"],
                "path_type": dependencies["Path"],
                "safe_identifier": dependencies["safe_identifier"],
                "open_regular_under": dependencies["open_regular_under"],
                "pinned_file_response": dependencies["PinnedFileResponse"],
                "artifact_open_error": dependencies["ArtifactOpenError"],
                "http_exception": dependencies["HTTPException"],
            },
        ),
    ]
