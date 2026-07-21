from __future__ import annotations

import copy
import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import ai_client, config_manager, credential_store, paths
from zhiji_backend.main import app


def test_credential_store_module_exists():
    assert importlib.util.find_spec("zhiji_backend.credential_store") is not None


@pytest.fixture
def env_path(tmp_path, monkeypatch):
    path = tmp_path / "home" / ".env"
    monkeypatch.setattr(credential_store, "ENV_PATH", path)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    return path


def test_credential_store_atomically_creates_0600_env_and_updates_process_env(
    env_path, monkeypatch
):
    replace_calls: list[tuple[object, object, int]] = []
    real_replace = os.replace

    def replace(source, destination):
        replace_calls.append((source, destination, stat.S_IMODE(os.stat(source).st_mode)))
        real_replace(source, destination)

    monkeypatch.setattr(credential_store.os, "replace", replace)

    credential_store.set_api_key("new-secret")

    assert env_path.read_text(encoding="utf-8") == "AI_API_KEY=new-secret\n"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert os.environ["AI_API_KEY"] == "new-secret"
    assert len(replace_calls) == 1
    source, destination, source_mode = replace_calls[0]
    assert os.fspath(source).rsplit(os.sep, 1)[0] == os.fspath(env_path.parent)
    assert destination == env_path
    assert source_mode == 0o600


def test_credential_store_update_preserves_unrelated_lines(env_path):
    env_path.parent.mkdir(parents=True)
    env_path.write_text(
        "# local settings\nKI_API_TOKEN=access-token\nAI_API_KEY=old-secret\nOTHER=value\n",
        encoding="utf-8",
    )

    credential_store.set_api_key("replacement-secret")

    assert env_path.read_text(encoding="utf-8") == (
        "# local settings\n"
        "KI_API_TOKEN=access-token\n"
        "AI_API_KEY=replacement-secret\n"
        "OTHER=value\n"
    )
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_credential_store_failed_replace_rolls_back_file_and_process_env(
    env_path, monkeypatch
):
    env_path.parent.mkdir(parents=True)
    original = "AI_API_KEY=old-secret\nOTHER=value\n"
    env_path.write_text(original, encoding="utf-8")
    monkeypatch.setenv("AI_API_KEY", "old-secret")
    monkeypatch.setattr(
        credential_store.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        credential_store.set_api_key("new-secret")

    assert env_path.read_text(encoding="utf-8") == original
    assert os.environ["AI_API_KEY"] == "old-secret"
    assert list(env_path.parent.iterdir()) == [env_path]


def test_credential_store_rejects_symlink_env(env_path, tmp_path):
    env_path.parent.mkdir(parents=True)
    target = tmp_path / "target.env"
    target.write_text("AI_API_KEY=target-secret\n", encoding="utf-8")
    env_path.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        credential_store.set_api_key("new-secret")

    assert target.read_text(encoding="utf-8") == "AI_API_KEY=target-secret\n"


def test_credential_store_serializes_concurrent_writes(env_path):
    values = [f"secret-{index}" for index in range(12)]
    barrier = threading.Barrier(len(values))
    errors: list[BaseException] = []

    def write(value):
        try:
            barrier.wait()
            credential_store.set_api_key(value)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(value,)) for value in values]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("AI_API_KEY=secret-")
    assert os.environ["AI_API_KEY"] == lines[0].split("=", 1)[1]


@pytest.mark.parametrize("key", ["bad\rkey", "bad\nkey", "bad\x00key"])
def test_credential_store_rejects_env_injection(env_path, key):
    with pytest.raises(ValueError, match="control"):
        credential_store.set_api_key(key)

    assert not env_path.exists()


@pytest.fixture
def config_client(tmp_path, monkeypatch):
    config_path = tmp_path / "data" / "system_config.json"
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(credential_store, "ENV_PATH", env_path)
    monkeypatch.setattr(paths, "ZHIJI_HOME", tmp_path)
    monkeypatch.setattr(config_manager, "_config", config_manager._defaults())
    monkeypatch.delenv("KI_AI_BASE_URL_ALLOWLIST", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    return TestClient(app), config_path


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown_root": True},
        {"general": {"unknown_general": True}},
        {"series": {"unknown_task": {"temperature": 0.2}}},
        {"series": {"paper": {"unknown_task_field": True}}},
        {"policy": {"allowlist": ["https://attacker.example/v1"]}},
        {"general": {"allowlist": ["https://attacker.example/v1"]}},
    ],
    ids=["root", "general", "module", "task", "policy-root", "policy-general"],
)
def test_unknown_system_config_fields_return_422(config_client, payload):
    client, _config_path = config_client

    response = client.put("/api/system-config", json=payload)

    assert response.status_code == 422


def test_frontend_full_get_put_roundtrip_preserves_response_contract(config_client):
    client, _config_path = config_client

    get_response = client.get("/api/system-config")
    put_response = client.put("/api/system-config", json=get_response.json())

    assert get_response.status_code == 200
    assert put_response.status_code == 200
    assert put_response.json() == {"status": "ok"}
    assert set(get_response.json()) == {
        "general",
        "ingest_pipeline",
        "series",
        "brainstorm",
        "briefing",
        "tasks",
        "concept",
        "study",
    }
    assert isinstance(get_response.json()["general"]["api_key"], str)


def test_sparse_known_update_merges_without_resetting_other_values(config_client):
    client, _config_path = config_client
    before = copy.deepcopy(config_manager.get_config())

    response = client.put(
        "/api/system-config",
        json={"series": {"paper": {"max_tokens": 12000}}},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    after = config_manager.get_config()
    assert after["series"]["paper"]["max_tokens"] == 12000
    assert after["series"]["paper"]["temperature"] == before["series"]["paper"]["temperature"]
    assert after["briefing"] == before["briefing"]


@pytest.mark.parametrize(
    ("module", "task"),
    [
        ("series", "discover_stage1"),
        ("series", "discover_stage2"),
        ("series", "discover_by_topic"),
        ("series", "expand"),
        ("series", "suggest_name"),
        ("study", "mistake_review"),
        ("study", "lecture_notes"),
        ("chain_analysis", "analyze"),
        ("chain_analysis", "report"),
        ("chain_analysis", "extract_hints"),
        ("chain_data_update", "ai_update"),
        ("chain_data_collect", "ai_collect"),
        ("chain_meta", "suggest_icon"),
        ("chain_chat", "chat"),
        ("chain_detector", "detect_hints"),
        ("chain_detector", "detect_new_chains"),
    ],
)
def test_sparse_schema_covers_current_ai_module_tasks(config_client, module, task):
    client, _config_path = config_client

    response = client.put(
        "/api/system-config",
        json={module: {task: {"temperature": 0.27}}},
    )

    assert response.status_code == 200
    assert config_manager.get_config()[module][task]["temperature"] == 0.27


def test_default_provider_url_is_allowed_and_trailing_slash_is_canonicalized(config_client):
    client, config_path = config_client

    response = client.put(
        "/api/system-config",
        json={"general": {"base_url": f"{config_manager.DEFAULT_AI_BASE_URL}/"}},
    )

    assert response.status_code == 200
    assert config_manager.get_config()["general"]["base_url"] == config_manager.DEFAULT_AI_BASE_URL
    assert json.loads(config_path.read_text(encoding="utf-8"))["general"]["base_url"] == config_manager.DEFAULT_AI_BASE_URL


def test_server_allowlist_expansion_accepts_canonical_exact_url(config_client, monkeypatch):
    client, _config_path = config_client
    monkeypatch.setenv(
        "KI_AI_BASE_URL_ALLOWLIST",
        "https://one.example/v1/, https://two.example/openai/v1",
    )

    response = client.put(
        "/api/system-config",
        json={"general": {"base_url": "https://two.example/openai/v1/"}},
    )

    assert response.status_code == 200
    assert config_manager.get_config()["general"]["base_url"] == "https://two.example/openai/v1"


def test_disallowed_provider_url_is_rejected_before_disk_or_memory_mutation(config_client):
    client, config_path = config_client
    config_manager.save_config()
    before_bytes = config_path.read_bytes()
    before_config = copy.deepcopy(config_manager.get_config())

    response = client.put(
        "/api/system-config",
        json={
            "general": {
                "base_url": "https://attacker.example/v1",
                "default_temperature": 0.91,
                "api_key": "must-not-be-written",
            }
        },
    )

    assert response.status_code == 422
    assert config_path.read_bytes() == before_bytes
    assert config_manager.get_config() == before_config
    assert not credential_store.ENV_PATH.exists()
    assert "AI_API_KEY" not in os.environ


def test_exact_returned_mask_and_empty_value_preserve_existing_credential(config_client):
    client, _config_path = config_client
    env_path = credential_store.ENV_PATH
    env_path.write_text("AI_API_KEY=abcdefghijklmnop\nOTHER=value\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    os.environ["AI_API_KEY"] = "abcdefghijklmnop"
    original = env_path.read_bytes()

    get_response = client.get("/api/system-config")
    payload = get_response.json()
    assert payload["general"]["api_key"] == "abcd****mnop"

    masked_response = client.put("/api/system-config", json=payload)
    payload["general"]["api_key"] = ""
    empty_response = client.put("/api/system-config", json=payload)

    assert masked_response.status_code == 200
    assert empty_response.status_code == 200
    assert env_path.read_bytes() == original
    assert os.environ["AI_API_KEY"] == "abcdefghijklmnop"


def test_new_key_replaces_credential_without_plaintext_get_or_json(config_client):
    client, config_path = config_client
    env_path = credential_store.ENV_PATH

    response = client.put(
        "/api/system-config",
        json={"general": {"api_key": "replacement-secret"}},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert env_path.read_text(encoding="utf-8") == "AI_API_KEY=replacement-secret\n"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert os.environ["AI_API_KEY"] == "replacement-secret"
    get_payload = client.get("/api/system-config").json()
    assert get_payload["general"]["api_key"] == "repl****cret"
    assert "replacement-secret" not in json.dumps(get_payload)
    persisted = config_path.read_text(encoding="utf-8")
    assert "replacement-secret" not in persisted
    assert "api_key" not in json.loads(persisted)["general"]


def test_api_key_update_is_immediately_visible_to_ai_client(config_client):
    client, _config_path = config_client

    response = client.put(
        "/api/system-config",
        json={"general": {"api_key": "immediate-secret"}},
    )

    assert response.status_code == 200
    assert ai_client._resolve_api_key({}) == "immediate-secret"


def test_ai_client_resolves_only_server_environment_in_priority_order(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert ai_client._resolve_api_key({"api_key": "json-secret"}) == ""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    assert ai_client._resolve_api_key({"api_key": "json-secret"}) == "deepseek-secret"
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    assert ai_client._resolve_api_key({"api_key": "json-secret"}) == "openai-secret"
    monkeypatch.setenv("AI_API_KEY", "ai-secret")
    assert ai_client._resolve_api_key({"api_key": "json-secret"}) == "ai-secret"


def test_defaults_and_module_config_never_expose_api_key(monkeypatch):
    monkeypatch.setattr(config_manager, "_config", config_manager._defaults())

    assert "api_key" not in config_manager._defaults()["general"]
    assert "api_key" not in config_manager.get_module_config("series", "paper")


@pytest.mark.parametrize("key", ["bad\rkey", "bad\nkey", "bad\x00key"])
def test_api_rejects_key_injection_without_mutation(config_client, key):
    client, config_path = config_client
    config_manager.save_config()
    before_config = config_path.read_bytes()
    before_memory = copy.deepcopy(config_manager.get_config())

    response = client.put(
        "/api/system-config",
        json={"general": {"api_key": key, "default_temperature": 0.88}},
    )

    assert response.status_code == 422
    assert config_path.read_bytes() == before_config
    assert config_manager.get_config() == before_memory
    assert not credential_store.ENV_PATH.exists()


def test_legacy_json_key_migrates_to_env_before_json_scrub(tmp_path, monkeypatch):
    config_path = tmp_path / "data" / "system_config.json"
    env_path = tmp_path / ".env"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "general": {
                    "api_key": "legacy-secret",
                    "base_url": config_manager.DEFAULT_AI_BASE_URL,
                },
                "series": {"paper": {"max_tokens": 15000}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(credential_store, "ENV_PATH", env_path)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    config_manager._config = {}

    loaded = config_manager.load_config()

    assert loaded["series"]["paper"]["max_tokens"] == 15000
    assert "api_key" not in loaded["general"]
    assert env_path.read_text(encoding="utf-8") == "AI_API_KEY=legacy-secret\n"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "api_key" not in persisted["general"]
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert os.environ["AI_API_KEY"] == "legacy-secret"


def test_legacy_migration_failure_is_fail_closed_without_key_loss(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    original = json.dumps({"general": {"api_key": "legacy-secret"}})
    config_path.write_text(original, encoding="utf-8")
    before_memory = {"sentinel": True}
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        credential_store,
        "set_api_key",
        lambda _key: (_ for _ in ()).throw(OSError("credential write failed")),
    )
    config_manager._config = before_memory

    with pytest.raises(OSError, match="credential write failed"):
        config_manager.load_config()

    assert config_path.read_text(encoding="utf-8") == original
    assert config_manager.get_config() is before_memory


def test_empty_legacy_key_is_scrubbed_without_creating_env(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    env_path = tmp_path / ".env"
    config_path.write_text(
        json.dumps({"general": {"api_key": "", "default_temperature": 0.21}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(credential_store, "ENV_PATH", env_path)
    config_manager._config = {}

    config_manager.load_config()

    assert "api_key" not in json.loads(config_path.read_text(encoding="utf-8"))["general"]
    assert not env_path.exists()


def test_config_write_and_existing_config_load_enforce_0600(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps({"general": {"default_temperature": 0.22}}),
        encoding="utf-8",
    )
    os.chmod(config_path, 0o644)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    config_manager._config = {}

    config_manager.load_config()
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    config_manager.save_config({"general": {"default_temperature": 0.33}})
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_cli_init_creates_env_and_config_with_0600_permissions(tmp_path):
    home = tmp_path / "zhiji-home"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(paths._PACKAGE_DIR.parent)

    result = subprocess.run(
        [sys.executable, "-m", "zhiji_backend.cli", "init", "--data-dir", str(home)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE((home / ".env").stat().st_mode) == 0o600
    config_path = home / "data" / "system_config.json"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert set(json.loads(config_path.read_text(encoding="utf-8"))) == {
        "general",
        "ingest_pipeline",
        "series",
        "brainstorm",
        "briefing",
        "tasks",
        "concept",
        "study",
    }
