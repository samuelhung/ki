import json
import os
import threading
from pathlib import Path

import pytest
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


def test_preflight_config_load_does_not_persist_normalization_before_backup_gate(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "system_config.json"
    original = json.dumps(
        {
            "digest_briefing": {
                "briefing_quick": {"max_tokens": 4096},
                "digest": {"max_tokens": 9999},
            },
            "knowledge_graph": {"entity_insight": {"max_tokens": 2048}},
        }
    )
    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    config_manager._config = {}

    loaded = config_manager.load_config(persist_normalization=False)

    assert loaded["briefing"]["briefing_quick"]["max_tokens"] == 4096
    assert config_path.read_text(encoding="utf-8") == original


def test_main_loads_and_persists_config_only_after_migration_gate():
    main_source = (ROOT / "src/zhiji_backend/main.py").read_text(encoding="utf-8")
    config_source = (ROOT / "src/zhiji_backend/config_manager.py").read_text(
        encoding="utf-8"
    )

    migration_index = main_source.index("ensure_migrations(get_db_path())")
    config_index = main_source.index("load_config()", migration_index)
    assert migration_index < config_index
    assert "load_config(persist_normalization=False)" in config_source


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


def _set_active_config(**overrides):
    config_manager._config = config_manager._deep_merge(config_manager._defaults(), overrides)


def test_save_config_normalizes_legacy_only_payload_and_preserves_active_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    _set_active_config(
        briefing={
            "briefing_quick": {"max_tokens": 3500},
            "briefing_daily": {"max_tokens": 9100},
        },
        series={"paper": {"max_tokens": 17000}},
    )

    config_manager.save_config(
        {
            "digest_briefing": {
                "digest": {"max_tokens": 9999},
                "briefing_quick": {"max_tokens": 4500},
            },
            "knowledge_graph": {"entity_insight": {"max_tokens": 99}},
        }
    )

    saved = config_manager.get_config()
    assert saved["briefing"]["briefing_quick"]["max_tokens"] == 4500
    assert saved["briefing"]["briefing_daily"]["max_tokens"] == 9100
    assert saved["series"]["paper"]["max_tokens"] == 17000
    assert "digest_briefing" not in saved
    assert "knowledge_graph" not in saved
    assert json.loads(config_path.read_text(encoding="utf-8")) == saved


def test_save_config_merges_canonical_only_payload_with_current_active_config(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    _set_active_config(briefing={"briefing_quick": {"max_tokens": 4200}})

    config_manager.save_config(
        {"briefing": {"briefing_daily": {"temperature": 0.19, "max_tokens": 9300}}}
    )

    saved = config_manager.get_config()
    assert saved["briefing"]["briefing_quick"]["max_tokens"] == 4200
    assert saved["briefing"]["briefing_daily"]["temperature"] == 0.19
    assert saved["briefing"]["briefing_daily"]["max_tokens"] == 9300


def test_save_config_mixed_payload_gives_canonical_briefing_values_precedence(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    _set_active_config()

    config_manager.save_config(
        {
            "digest_briefing": {
                "briefing_quick": {"temperature": 0.11, "max_tokens": 4100},
                "briefing_daily": {"max_tokens": 9200},
            },
            "briefing": {"briefing_quick": {"max_tokens": 5100}},
        }
    )

    saved = config_manager.get_config()
    assert saved["briefing"]["briefing_quick"]["temperature"] == 0.11
    assert saved["briefing"]["briefing_quick"]["max_tokens"] == 5100
    assert saved["briefing"]["briefing_daily"]["max_tokens"] == 9200


def test_save_config_preserves_unrelated_modules_omitted_by_stale_client(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    _set_active_config(
        ingest_pipeline={"summarize": {"max_tokens": 3900}},
        custom_module={"custom_task": {"temperature": 0.77}},
    )

    config_manager.save_config({"general": {"default_temperature": 0.25}})

    saved = config_manager.get_config()
    assert saved["general"]["default_temperature"] == 0.25
    assert saved["ingest_pipeline"]["summarize"]["max_tokens"] == 3900
    assert saved["custom_module"] == {"custom_task": {"temperature": 0.77}}


def test_write_config_uses_same_directory_temp_fsync_and_atomic_replace(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    fsync_calls: list[int] = []
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    monkeypatch.setattr(config_manager.os, "fsync", fsync_calls.append, raising=False)

    def replace(source, destination):
        replace_calls.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(config_manager.os, "replace", replace, raising=False)

    config_manager._write_config({"briefing": {"briefing_quick": {"max_tokens": 4444}}})

    assert len(fsync_calls) == 2
    assert len(replace_calls) == 1
    source, destination = replace_calls[0]
    assert source.parent == config_path.parent
    assert destination == config_path
    assert not source.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["briefing"]["briefing_quick"]["max_tokens"] == 4444


def test_parent_directory_fsync_closes_fd_when_sync_is_unsupported(tmp_path, monkeypatch):
    monkeypatch.setattr(config_manager, "CONFIG_PATH", tmp_path / "system_config.json")
    closed: list[int] = []
    monkeypatch.setattr(config_manager.os, "open", lambda *_: 73)
    monkeypatch.setattr(
        config_manager.os,
        "fsync",
        lambda *_: (_ for _ in ()).throw(OSError("directory fsync unsupported")),
    )
    monkeypatch.setattr(config_manager.os, "close", closed.append)

    config_manager._fsync_parent_directory()

    assert closed == [73]


def test_atomic_write_failure_preserves_existing_file_and_cleans_temp(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    config_path.write_text('{"existing": true}', encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        config_manager.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
        raising=False,
    )

    with pytest.raises(OSError, match="replace failed"):
        config_manager._write_config({"replacement": True})

    assert config_path.read_text(encoding="utf-8") == '{"existing": true}'
    assert list(tmp_path.iterdir()) == [config_path]


def test_save_failure_does_not_replace_active_in_memory_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config_manager, "CONFIG_PATH", tmp_path / "system_config.json")
    _set_active_config(briefing={"briefing_quick": {"max_tokens": 4300}})
    before = config_manager.get_config()
    monkeypatch.setattr(
        config_manager,
        "_write_config",
        lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        config_manager.save_config(
            {"digest_briefing": {"briefing_quick": {"max_tokens": 5300}}}
        )

    assert config_manager.get_config() is before
    assert config_manager.get_config()["briefing"]["briefing_quick"]["max_tokens"] == 4300


def test_overlapping_saves_are_serialized_without_losing_merges(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    _set_active_config()
    real_write = config_manager._write_config
    first_in_writer = threading.Event()
    release_first = threading.Event()
    second_entered_writer = threading.Event()
    second_attempted_lock = threading.Event()
    second_done = threading.Event()
    write_count = 0
    count_lock = threading.Lock()
    errors: list[BaseException] = []

    class TrackingRLock:
        def __init__(self):
            self._lock = threading.RLock()
            self._attempts = 0
            self._attempts_lock = threading.Lock()

        def __enter__(self):
            with self._attempts_lock:
                attempt = self._attempts
                self._attempts += 1
            if attempt == 1:
                second_attempted_lock.set()
            self._lock.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self._lock.release()

    monkeypatch.setattr(config_manager, "_config_lock", TrackingRLock())

    def overlapping_write(config):
        nonlocal write_count
        with count_lock:
            write_index = write_count
            write_count += 1
        if write_index == 0:
            first_in_writer.set()
            assert release_first.wait(2)
        else:
            second_entered_writer.set()
        real_write(config)

    monkeypatch.setattr(config_manager, "_write_config", overlapping_write)

    def run_save(payload, *, done=None):
        try:
            config_manager.save_config(payload)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if done:
                done.set()

    first = threading.Thread(
        target=run_save,
        args=({"briefing": {"briefing_quick": {"max_tokens": 4800}}},),
    )
    second = threading.Thread(
        target=run_save,
        args=({"series": {"paper": {"max_tokens": 18000}}},),
        kwargs={"done": second_done},
    )

    first.start()
    assert first_in_writer.wait(2)
    second.start()
    assert second_attempted_lock.wait(2)
    try:
        second_reached_writer_while_first_blocked = second_entered_writer.is_set()
    finally:
        release_first.set()
        first.join(2)
        second.join(2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert second_done.is_set()
    assert second_reached_writer_while_first_blocked is False
    active = config_manager.get_config()
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted == active
    assert active["briefing"]["briefing_quick"]["max_tokens"] == 4800
    assert active["series"]["paper"]["max_tokens"] == 18000


def test_load_keeps_normalized_config_when_migration_persistence_fails(
    tmp_path, monkeypatch, caplog
):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps(
            {
                "digest_briefing": {"briefing_quick": {"max_tokens": 4700}},
                "general": {"base_url": "https://parsed.example.test/v1"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        config_manager,
        "_write_config",
        lambda *_: (_ for _ in ()).throw(OSError("read-only filesystem")),
    )
    config_manager._config = {}

    loaded = config_manager.load_config()

    assert loaded["briefing"]["briefing_quick"]["max_tokens"] == 4700
    assert loaded["general"]["base_url"] == "https://parsed.example.test/v1"
    assert "digest_briefing" not in loaded
    assert "Failed to persist normalized system config" in caplog.text


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
