from __future__ import annotations

import inspect
import re
from pathlib import Path

from zhiji_backend import summarizer
from zhiji_backend.main import app


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "src" / "zhiji_backend"
MIGRATION_PATH = Path("migrations.py")
GRAPH_PERSISTENCE_PATTERNS = {
    "entities": re.compile(
        r'''["']entities["']|\b(?:FROM|JOIN|INTO|UPDATE|REFERENCES|TABLE(?:\s+IF\s+NOT\s+EXISTS)?)\s+entities\b|\bidx_entities\b''',
        re.IGNORECASE,
    ),
    "event_entities": re.compile(r"\bevent_entities\b"),
    "entity_relations": re.compile(r"\bentity_relations\b"),
}


def test_active_backend_has_no_knowledge_graph_feature_surface():
    backend_sources = {
        path.relative_to(BACKEND_ROOT): path.read_text(encoding="utf-8")
        for path in BACKEND_ROOT.rglob("*.py")
    }
    active_source = "\n".join(backend_sources.values())

    assert not (BACKEND_ROOT / "routes" / "entity_routes.py").exists()
    for retired_symbol in (
        "entity_routes",
        "/api/entities",
        "_extract_entities",
        "_store_entities",
    ):
        assert retired_symbol not in active_source

    assert {
        path for path, source in backend_sources.items() if "knowledge_graph" in source
    } == {Path("config_manager.py"), MIGRATION_PATH}

    assert not any(
        getattr(route, "path", "").startswith("/api/entities")
        for route in app.routes
    )


def test_graph_persistence_tables_are_not_referenced_by_active_code():
    backend_sources = {
        path.relative_to(BACKEND_ROOT): path.read_text(encoding="utf-8")
        for path in BACKEND_ROOT.rglob("*.py")
    }

    for table_name, pattern in GRAPH_PERSISTENCE_PATTERNS.items():
        reference_paths = {
            path
            for path, source in backend_sources.items()
            if pattern.search(source)
        }
        assert reference_paths == {MIGRATION_PATH}, (
            f"{table_name} references must remain isolated to {MIGRATION_PATH}: "
            f"{sorted(str(path) for path in reference_paths)}"
        )


def test_brainstorm_keeps_generic_entity_id_contract():
    brainstorm_source = (BACKEND_ROOT / "routes" / "brainstorm_routes.py").read_text(encoding="utf-8")

    assert "entity_id: str" in brainstorm_source
    assert '"entity_id": request.entity_id' in brainstorm_source


def test_summarizer_signature_has_no_entity_extraction_switch():
    parameters = inspect.signature(summarizer.summarize_transcript).parameters

    assert "extract_entities" not in parameters


def test_summarization_uses_one_ai_call_and_returns_summary_only(monkeypatch):
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return "## 概述\n测试概述。\n\n## 核心论点\n测试论点。"

    monkeypatch.setattr(summarizer, "chat", fake_chat)

    result = summarizer.summarize_transcript("测试文本" * 30, title="测试标题")

    assert len(calls) == 1
    assert result == {"summary": "## 核心论点\n测试论点。", "overview": "测试概述。"}
