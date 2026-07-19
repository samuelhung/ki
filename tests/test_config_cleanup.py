import json
from pathlib import Path

from fastapi.testclient import TestClient

from zhiji_backend import config_manager
from zhiji_backend.db import init_db
from zhiji_backend.main import app


ROOT = Path(__file__).resolve().parents[1]


def _load_from(config_path: Path, monkeypatch):
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    config_manager._config = {}
    return config_manager.load_config()


def test_defaults_expose_only_active_briefing_tasks():
    defaults = config_manager._defaults()

    assert set(defaults["briefing"]) == {"briefing_quick", "briefing_daily"}
    assert "digest_briefing" not in defaults
    assert "knowledge_graph" not in defaults


def test_load_config_normalizes_retired_modules_without_losing_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps(
            {
                "general": {"base_url": "https://ai.example.test/v1"},
                "digest_briefing": {
                    "digest": {"max_tokens": 9999},
                    "briefing_quick": {"max_tokens": 4096, "thinking": True},
                    "briefing_daily": {"temperature": 0.17},
                },
                "knowledge_graph": {"entity_insight": {"max_tokens": 2048}},
                "custom_module": {"custom_task": {"max_tokens": 77}},
            }
        ),
        encoding="utf-8",
    )

    loaded = _load_from(config_path, monkeypatch)

    assert loaded["briefing"]["briefing_quick"]["max_tokens"] == 4096
    assert loaded["briefing"]["briefing_quick"]["thinking"] is True
    assert loaded["briefing"]["briefing_daily"]["temperature"] == 0.17
    assert loaded["general"]["base_url"] == "https://ai.example.test/v1"
    assert loaded["custom_module"] == {"custom_task": {"max_tokens": 77}}
    assert set(loaded["briefing"]) == {"briefing_quick", "briefing_daily"}
    assert "digest_briefing" not in loaded
    assert "knowledge_graph" not in loaded

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["general"] == {"base_url": "https://ai.example.test/v1"}
    assert persisted["custom_module"] == {"custom_task": {"max_tokens": 77}}
    assert persisted["briefing"] == {
        "briefing_quick": {"max_tokens": 4096, "thinking": True},
        "briefing_daily": {"temperature": 0.17},
    }
    assert "digest_briefing" not in persisted
    assert "knowledge_graph" not in persisted


def test_new_briefing_overrides_take_precedence_over_legacy_values(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps(
            {
                "digest_briefing": {
                    "briefing_quick": {"temperature": 0.12, "max_tokens": 4000},
                    "briefing_daily": {"max_tokens": 7000},
                },
                "briefing": {
                    "briefing_quick": {"max_tokens": 5000},
                    "digest": {"max_tokens": 1234},
                    "retired_task": {"thinking": True},
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = _load_from(config_path, monkeypatch)

    assert loaded["briefing"]["briefing_quick"]["temperature"] == 0.12
    assert loaded["briefing"]["briefing_quick"]["max_tokens"] == 5000
    assert loaded["briefing"]["briefing_daily"]["max_tokens"] == 7000
    assert set(loaded["briefing"]) == {"briefing_quick", "briefing_daily"}


def test_normalized_config_is_persisted_once_and_reload_is_idempotent(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps(
            {
                "digest_briefing": {
                    "digest": {"max_tokens": 9999},
                    "briefing_quick": {"max_tokens": 4096},
                }
            }
        ),
        encoding="utf-8",
    )
    writes: list[dict] = []

    def write_config(config):
        writes.append(config)
        config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "_write_config", write_config, raising=False)
    config_manager._config = {}

    first = config_manager.load_config()
    second = config_manager.load_config()

    assert first == second
    assert len(writes) == 1
    assert writes[0] == {"briefing": {"briefing_quick": {"max_tokens": 4096}}}


def test_already_normalized_config_is_not_rewritten(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps({"briefing": {"briefing_daily": {"max_tokens": 9000}}}),
        encoding="utf-8",
    )
    writes: list[dict] = []
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "_write_config", writes.append, raising=False)
    config_manager._config = {}

    loaded = config_manager.load_config()

    assert loaded["briefing"]["briefing_daily"]["max_tokens"] == 9000
    assert writes == []


def test_daily_digest_surfaces_are_retired():
    retired_paths = [
        ROOT / "src/zhiji_backend/digest_ai.py",
        ROOT / "src/zhiji_backend/routes/digest_routes.py",
        ROOT / "tests/test_digest_api.py",
    ]
    for path in retired_paths:
        assert not path.exists(), path

    active_sources = [
        ROOT / "src/zhiji_backend/main.py",
        ROOT / "src/zhiji_backend/prompt_registry.py",
        ROOT / "src/zhiji_backend/briefing.py",
        ROOT / "src/zhiji_backend/routes/system_routes.py",
        ROOT / "app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx",
        ROOT / "app/frontend/src/components/cinematic-system/systemTypes.ts",
        ROOT / "app/frontend/src/components/cinematic-system/SystemAssetBox.tsx",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_sources)

    assert "digest_routes" not in combined
    assert "digest_ai" not in combined
    assert "digest_briefing" not in combined
    assert "Daily Digest" not in combined
    assert "每日摘要" not in combined
    assert "fileCount('digests')" not in combined


def test_system_inventory_hides_digest_table_and_files_but_keeps_briefings(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()

    response = TestClient(app).get("/api/system/database")

    assert response.status_code == 200
    payload = response.json()
    assert "digests" not in payload["database"]["tables"]
    assert "digests" not in payload["files"]
    assert "briefings" in payload["database"]["tables"]
