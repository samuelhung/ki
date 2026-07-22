from __future__ import annotations

import argparse
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


def test_credential_store_never_chmods_destination_after_replace(env_path, monkeypatch):
    real_chmod = credential_store.os.chmod

    def chmod(path, mode):
        if os.fspath(path) == os.fspath(env_path):
            raise AssertionError("destination chmod occurred after replace")
        real_chmod(path, mode)

    monkeypatch.setattr(credential_store.os, "chmod", chmod)

    credential_store.set_api_key("committed-secret")

    assert env_path.read_text(encoding="utf-8") == "AI_API_KEY=committed-secret\n"
    assert os.environ["AI_API_KEY"] == "committed-secret"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_credential_store_parent_fsync_failure_propagates_with_coherent_bundle(
    env_path, monkeypatch
):
    env_path.parent.mkdir(parents=True)
    env_path.write_text(
        f"AI_BASE_URL={config_manager.DEFAULT_AI_BASE_URL}\n"
        "AI_API_KEY=old-secret\n",
        encoding="utf-8",
    )
    os.chmod(env_path, 0o600)
    monkeypatch.setenv("AI_BASE_URL", config_manager.DEFAULT_AI_BASE_URL)
    monkeypatch.setenv("AI_API_KEY", "old-secret")
    monkeypatch.setattr(
        credential_store,
        "_fsync_parent",
        lambda _path: (_ for _ in ()).throw(OSError("directory fsync failed")),
    )

    with pytest.raises(OSError, match="directory fsync failed"):
        credential_store.set_provider_bundle(
            "committed-secret",
            "https://provider-new.example/v1",
        )

    assert env_path.read_text(encoding="utf-8") == (
        "AI_BASE_URL=https://provider-new.example/v1\n"
        "AI_API_KEY=committed-secret\n"
    )
    assert os.environ["AI_BASE_URL"] == "https://provider-new.example/v1"
    assert os.environ["AI_API_KEY"] == "committed-secret"


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
    monkeypatch.delenv("AI_BASE_URL", raising=False)
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
    get_response = client.get("/api/system-config")
    payload = get_response.json()
    assert payload["general"]["api_key"] == "abcd****mnop"

    masked_response = client.put("/api/system-config", json=payload)
    payload["general"]["api_key"] = ""
    empty_response = client.put("/api/system-config", json=payload)

    assert masked_response.status_code == 200
    assert empty_response.status_code == 200
    assert env_path.read_text(encoding="utf-8") == (
        "OTHER=value\n"
        f"AI_BASE_URL={config_manager.DEFAULT_AI_BASE_URL}\n"
        "AI_API_KEY=abcdefghijklmnop\n"
    )
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
    assert env_path.read_text(encoding="utf-8") == (
        f"AI_BASE_URL={config_manager.DEFAULT_AI_BASE_URL}\n"
        "AI_API_KEY=replacement-secret\n"
    )
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


def test_config_and_credential_updates_are_serialized_as_one_transaction(
    config_client, monkeypatch
):
    _client, config_path = config_client
    monkeypatch.setenv(
        "KI_AI_BASE_URL_ALLOWLIST",
        "https://provider-a.example/v1,https://provider-b.example/v1",
    )
    config_manager.save_config()
    real_write_config = config_manager._write_config
    real_set_provider_bundle = credential_store.set_provider_bundle
    first_config_write = threading.Event()
    release_first = threading.Event()
    second_credential_write = threading.Event()
    write_count = 0
    count_lock = threading.Lock()
    responses: dict[str, int] = {}
    errors: list[BaseException] = []

    def blocking_write(config):
        nonlocal write_count
        with count_lock:
            index = write_count
            write_count += 1
        if index == 0:
            first_config_write.set()
            assert release_first.wait(2)
        real_write_config(config)

    def tracking_set_provider_bundle(key, base_url):
        if key == "key-b":
            second_credential_write.set()
        real_set_provider_bundle(key, base_url)

    monkeypatch.setattr(config_manager, "_write_config", blocking_write)
    monkeypatch.setattr(
        credential_store,
        "set_provider_bundle",
        tracking_set_provider_bundle,
    )

    def update(name, base_url, key):
        try:
            response = TestClient(app).put(
                "/api/system-config",
                json={"general": {"base_url": base_url, "api_key": key}},
            )
            responses[name] = response.status_code
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(
        target=update,
        args=("a", "https://provider-a.example/v1", "key-a"),
    )
    second = threading.Thread(
        target=update,
        args=("b", "https://provider-b.example/v1", "key-b"),
    )

    first.start()
    assert first_config_write.wait(2)
    second.start()
    second_entered_while_first_blocked = second_credential_write.wait(0.2)
    release_first.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert responses == {"a": 200, "b": 200}
    assert second_entered_while_first_blocked is False
    assert os.environ["AI_API_KEY"] == "key-b"
    assert credential_store.ENV_PATH.read_text(encoding="utf-8") == (
        "AI_BASE_URL=https://provider-b.example/v1\n"
        "AI_API_KEY=key-b\n"
    )
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["general"]["base_url"] == "https://provider-b.example/v1"
    assert config_manager.get_config()["general"]["base_url"] == "https://provider-b.example/v1"


def test_config_get_waits_for_transaction_and_returns_matching_credential(
    config_client, monkeypatch
):
    _client, _config_path = config_client
    monkeypatch.setenv(
        "KI_AI_BASE_URL_ALLOWLIST",
        "https://provider-a.example/v1",
    )
    config_manager.save_config()
    credential_store.set_api_key("old-secret")
    real_write_config = config_manager._write_config
    config_write_blocked = threading.Event()
    release_write = threading.Event()
    get_done = threading.Event()
    results: dict[str, object] = {}

    def blocking_write(config):
        config_write_blocked.set()
        assert release_write.wait(2)
        real_write_config(config)

    monkeypatch.setattr(config_manager, "_write_config", blocking_write)

    def update():
        results["put"] = TestClient(app).put(
            "/api/system-config",
            json={
                "general": {
                    "base_url": "https://provider-a.example/v1",
                    "api_key": "new-secret",
                }
            },
        )

    def read():
        results["get"] = TestClient(app).get("/api/system-config")
        get_done.set()

    writer = threading.Thread(target=update)
    reader = threading.Thread(target=read)
    writer.start()
    assert config_write_blocked.wait(2)
    reader.start()
    get_completed_while_write_blocked = get_done.wait(0.2)
    release_write.set()
    writer.join(2)
    reader.join(2)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert get_completed_while_write_blocked is False
    assert results["put"].status_code == 200
    assert results["get"].status_code == 200
    payload = results["get"].json()
    assert payload["general"]["base_url"] == "https://provider-a.example/v1"
    assert payload["general"]["api_key"] == "new-****cret"


def test_config_write_failure_rolls_back_credential_disk_memory_and_env(
    config_client, monkeypatch
):
    client, config_path = config_client
    config_manager.save_config()
    credential_store.set_api_key("old-secret")
    before_config_bytes = config_path.read_bytes()
    before_env_bytes = credential_store.ENV_PATH.read_bytes()
    before_memory = config_manager.get_config()
    monkeypatch.setattr(
        config_manager,
        "_write_config",
        lambda _config: (_ for _ in ()).throw(OSError("config replace failed")),
    )

    with pytest.raises(OSError, match="config replace failed"):
        client.put(
            "/api/system-config",
            json={
                "general": {
                    "default_temperature": 0.81,
                    "api_key": "new-secret",
                }
            },
        )

    assert config_path.read_bytes() == before_config_bytes
    assert credential_store.ENV_PATH.read_bytes() == before_env_bytes
    assert config_manager.get_config() is before_memory
    assert os.environ["AI_API_KEY"] == "old-secret"


def test_env_directory_fsync_failure_skips_json_and_restarts_with_paired_bundle(
    config_client, monkeypatch
):
    client, config_path = config_client
    new_url = "https://provider-new.example/v1"
    monkeypatch.setenv("KI_AI_BASE_URL_ALLOWLIST", new_url)
    config_manager.save_config()
    credential_store.set_provider_bundle(
        "old-secret",
        config_manager.DEFAULT_AI_BASE_URL,
    )
    env_path = credential_store.ENV_PATH
    before_config = config_path.read_bytes()
    real_write_config = config_manager._write_config
    real_fsync_parent = credential_store._fsync_parent
    config_writes: list[dict] = []

    def tracking_write_config(config):
        config_writes.append(config)
        real_write_config(config)

    monkeypatch.setattr(config_manager, "_write_config", tracking_write_config)
    monkeypatch.setattr(
        credential_store,
        "_fsync_parent",
        lambda _path: (_ for _ in ()).throw(OSError("directory fsync failed")),
    )

    with pytest.raises(OSError, match="directory fsync failed"):
        client.put(
            "/api/system-config",
            json={"general": {"base_url": new_url, "api_key": "new-secret"}},
        )

    assert config_writes == []
    assert config_path.read_bytes() == before_config
    env_values = dict(
        line.split("=", 1)
        for line in credential_store.ENV_PATH.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    disk_bundle = (env_values["AI_BASE_URL"], env_values["AI_API_KEY"])
    assert disk_bundle in {
        (config_manager.DEFAULT_AI_BASE_URL, "old-secret"),
        (new_url, "new-secret"),
    }
    assert (os.environ["AI_BASE_URL"], os.environ["AI_API_KEY"]) == disk_bundle

    monkeypatch.setattr(config_manager, "_write_config", real_write_config)
    monkeypatch.setattr(credential_store, "_fsync_parent", real_fsync_parent)
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    credential_store.load_hardened_env(env_path)
    config_manager._config = {}

    config_manager.load_config()
    restarted_config, restarted_key = config_manager.get_config_and_credential()

    assert (
        restarted_config["general"]["base_url"],
        restarted_key,
    ) == disk_bundle
    assert json.loads(config_path.read_text(encoding="utf-8"))["general"][
        "base_url"
    ] == disk_bundle[0]


def test_partial_credential_failure_rolls_back_both_transaction_states(
    config_client, monkeypatch
):
    client, config_path = config_client
    config_manager.save_config()
    credential_store.set_api_key("old-secret")
    before_config_bytes = config_path.read_bytes()
    before_env_bytes = credential_store.ENV_PATH.read_bytes()
    before_memory = config_manager.get_config()

    def partial_credential_write(_key, _base_url):
        credential_store.ENV_PATH.write_text(
            "AI_BASE_URL=https://partial.example/v1\nAI_API_KEY=partial-secret\n",
            encoding="utf-8",
        )
        os.environ["AI_BASE_URL"] = "https://partial.example/v1"
        os.environ["AI_API_KEY"] = "partial-secret"
        raise OSError("credential commit failed")

    monkeypatch.setattr(
        credential_store,
        "set_provider_bundle",
        partial_credential_write,
    )

    with pytest.raises(OSError, match="credential commit failed"):
        client.put(
            "/api/system-config",
            json={
                "general": {
                    "default_temperature": 0.82,
                    "api_key": "new-secret",
                }
            },
        )

    assert config_path.read_bytes() == before_config_bytes
    assert credential_store.ENV_PATH.read_bytes() == before_env_bytes
    assert config_manager.get_config() is before_memory
    assert "AI_BASE_URL" not in os.environ
    assert os.environ["AI_API_KEY"] == "old-secret"


def test_precommit_credential_replace_failure_does_not_rewrite_snapshots(
    config_client, monkeypatch
):
    client, config_path = config_client
    config_manager.save_config()
    credential_store.set_api_key("old-secret")
    before_config_bytes = config_path.read_bytes()
    before_env_bytes = credential_store.ENV_PATH.read_bytes()
    before_memory = config_manager.get_config()
    monkeypatch.setattr(
        credential_store.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("credential replace failed")),
    )

    with pytest.raises(OSError, match="credential replace failed"):
        client.put(
            "/api/system-config",
            json={
                "general": {
                    "default_temperature": 0.83,
                    "api_key": "new-secret",
                }
            },
        )

    assert config_path.read_bytes() == before_config_bytes
    assert credential_store.ENV_PATH.read_bytes() == before_env_bytes
    assert config_manager.get_config() is before_memory
    assert os.environ["AI_API_KEY"] == "old-secret"


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


@pytest.mark.parametrize(
    ("env_url", "json_url", "expected_url"),
    [
        (
            config_manager.DEFAULT_AI_BASE_URL,
            config_manager.DEFAULT_AI_BASE_URL,
            config_manager.DEFAULT_AI_BASE_URL,
        ),
        (
            "https://provider-new.example/v1",
            config_manager.DEFAULT_AI_BASE_URL,
            "https://provider-new.example/v1",
        ),
        (
            "https://provider-new.example/v1",
            "https://provider-new.example/v1",
            "https://provider-new.example/v1",
        ),
    ],
    ids=["before-env-replace", "after-env-before-json", "after-json-mirror"],
)
def test_restart_uses_atomic_env_bundle_at_every_write_boundary(
    tmp_path, monkeypatch, env_url, json_url, expected_url
):
    config_path = tmp_path / "system_config.json"
    env_path = tmp_path / ".env"
    config_path.write_text(
        json.dumps({"general": {"base_url": json_url}}),
        encoding="utf-8",
    )
    env_path.write_text(
        f"AI_BASE_URL={env_url}\nAI_API_KEY=bundle-secret\n",
        encoding="utf-8",
    )
    os.chmod(env_path, 0o600)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(credential_store, "ENV_PATH", env_path)
    monkeypatch.setenv(
        "KI_AI_BASE_URL_ALLOWLIST",
        "https://provider-new.example/v1",
    )
    monkeypatch.setenv("AI_BASE_URL", env_url)
    monkeypatch.setenv("AI_API_KEY", "bundle-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config_manager._config = {}

    config_manager.load_config()
    snapshot, key = config_manager.get_config_and_credential()

    assert key == "bundle-secret"
    assert snapshot["general"]["base_url"] == expected_url
    assert json.loads(config_path.read_text(encoding="utf-8"))["general"]["base_url"] == expected_url


def test_existing_install_without_env_url_uses_json_url_and_env_key(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps({"general": {"base_url": "https://legacy.example/v1"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setenv("KI_AI_BASE_URL_ALLOWLIST", "https://legacy.example/v1")
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-env-secret")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config_manager._config = {}

    config_manager.load_config()
    snapshot, key = config_manager.get_config_and_credential()

    assert snapshot["general"]["base_url"] == "https://legacy.example/v1"
    assert key == "legacy-env-secret"


def test_authoritative_env_url_does_not_pair_with_fallback_credential(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps({"general": {"base_url": config_manager.DEFAULT_AI_BASE_URL}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setenv("AI_BASE_URL", config_manager.DEFAULT_AI_BASE_URL)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unpaired-fallback-secret")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config_manager._config = {}

    config_manager.load_config()
    snapshot, key = config_manager.get_config_and_credential()

    assert snapshot["general"]["base_url"] == config_manager.DEFAULT_AI_BASE_URL
    assert key == ""


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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config_manager._config = {}

    loaded = config_manager.load_config()

    assert loaded["series"]["paper"]["max_tokens"] == 15000
    assert "api_key" not in loaded["general"]
    assert env_path.read_text(encoding="utf-8") == (
        f"AI_BASE_URL={config_manager.DEFAULT_AI_BASE_URL}\n"
        "AI_API_KEY=legacy-secret\n"
    )
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "api_key" not in persisted["general"]
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert os.environ["AI_API_KEY"] == "legacy-secret"


def test_legacy_json_key_does_not_override_existing_server_credential(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "system_config.json"
    env_path = tmp_path / ".env"
    config_path.write_text(
        json.dumps(
            {
                "general": {
                    "api_key": "legacy-secret",
                    "default_temperature": 0.23,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(credential_store, "ENV_PATH", env_path)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "server-secret")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config_manager._config = {}

    loaded = config_manager.load_config()

    assert "api_key" not in loaded["general"]
    assert credential_store.resolve_api_key() == "server-secret"
    assert os.environ["AI_BASE_URL"] == config_manager.DEFAULT_AI_BASE_URL
    assert os.environ["AI_API_KEY"] == "server-secret"
    assert os.environ["OPENAI_API_KEY"] == "server-secret"
    assert env_path.read_text(encoding="utf-8") == (
        f"AI_BASE_URL={config_manager.DEFAULT_AI_BASE_URL}\n"
        "AI_API_KEY=server-secret\n"
    )
    assert "api_key" not in json.loads(config_path.read_text(encoding="utf-8"))["general"]


def test_legacy_migration_failure_is_fail_closed_without_key_loss(tmp_path, monkeypatch):
    config_path = tmp_path / "system_config.json"
    original = json.dumps({"general": {"api_key": "legacy-secret"}})
    config_path.write_text(original, encoding="utf-8")
    before_memory = {"sentinel": True}
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        credential_store,
        "set_provider_bundle",
        lambda _key, _base_url: (_ for _ in ()).throw(
            OSError("credential write failed")
        ),
    )
    config_manager._config = before_memory

    with pytest.raises(OSError, match="credential write failed"):
        config_manager.load_config()

    assert config_path.read_text(encoding="utf-8") == original
    assert config_manager.get_config() is before_memory


def test_legacy_config_scrub_failure_rolls_back_migrated_credential(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "system_config.json"
    env_path = tmp_path / ".env"
    original = json.dumps(
        {"general": {"api_key": "legacy-secret", "default_temperature": 0.24}}
    )
    config_path.write_text(original, encoding="utf-8")
    before_memory = {"sentinel": True}
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(credential_store, "ENV_PATH", env_path)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        config_manager,
        "_write_config",
        lambda _config: (_ for _ in ()).throw(OSError("config scrub failed")),
    )
    config_manager._config = before_memory

    with pytest.raises(OSError, match="config scrub failed"):
        config_manager.load_config()

    assert config_path.read_text(encoding="utf-8") == original
    assert not env_path.exists()
    assert "AI_API_KEY" not in os.environ
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
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
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


def test_config_load_rejects_symlink_without_touching_target(tmp_path, monkeypatch):
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps({"general": {"default_temperature": 0.44}}),
        encoding="utf-8",
    )
    os.chmod(target, 0o644)
    config_path = tmp_path / "system_config.json"
    config_path.symlink_to(target)
    original_bytes = target.read_bytes()
    original_mode = stat.S_IMODE(target.stat().st_mode)
    before_memory = {"sentinel": True}
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    config_manager._config = before_memory

    with pytest.raises(OSError, match="symlink"):
        config_manager.load_config()

    assert config_path.is_symlink()
    assert target.read_bytes() == original_bytes
    assert stat.S_IMODE(target.stat().st_mode) == original_mode
    assert config_manager.get_config() is before_memory


def test_config_save_rejects_symlink_without_touching_target(tmp_path, monkeypatch):
    target = tmp_path / "target.json"
    target.write_text('{"target": true}', encoding="utf-8")
    os.chmod(target, 0o644)
    config_path = tmp_path / "system_config.json"
    config_path.symlink_to(target)
    original_bytes = target.read_bytes()
    original_mode = stat.S_IMODE(target.stat().st_mode)
    before_memory = config_manager._defaults()
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    config_manager._config = before_memory

    with pytest.raises(OSError, match="symlink"):
        config_manager.save_config({"general": {"default_temperature": 0.45}})

    assert config_path.is_symlink()
    assert target.read_bytes() == original_bytes
    assert stat.S_IMODE(target.stat().st_mode) == original_mode
    assert config_manager.get_config() is before_memory


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


def test_cli_serve_hardens_existing_env_before_loading_preserved_credentials(
    tmp_path, monkeypatch
):
    from zhiji_backend import cli
    import uvicorn

    home = tmp_path / "selected-home"
    home.mkdir()
    env_path = home / ".env"
    env_path.write_text(
        f"AI_BASE_URL={config_manager.DEFAULT_AI_BASE_URL}\n"
        "AI_API_KEY=preserved-secret\n",
        encoding="utf-8",
    )
    os.chmod(env_path, 0o644)
    calls = []
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    cli.cmd_serve(argparse.Namespace(data_dir=str(home), host="127.0.0.1", port=9120))

    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert os.environ["AI_BASE_URL"] == config_manager.DEFAULT_AI_BASE_URL
    assert os.environ["AI_API_KEY"] == "preserved-secret"
    assert len(calls) == 1


def test_cli_serve_rejects_symlink_env_without_touching_target(tmp_path, monkeypatch):
    from zhiji_backend import cli
    import uvicorn

    home = tmp_path / "selected-home"
    home.mkdir()
    target = tmp_path / "target.env"
    target.write_text("AI_API_KEY=target-secret\n", encoding="utf-8")
    os.chmod(target, 0o644)
    env_path = home / ".env"
    env_path.symlink_to(target)
    original = target.read_bytes()
    original_mode = stat.S_IMODE(target.stat().st_mode)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: None)

    with pytest.raises(OSError, match="symlink"):
        cli.cmd_serve(
            argparse.Namespace(data_dir=str(home), host="127.0.0.1", port=9120)
        )

    assert env_path.is_symlink()
    assert target.read_bytes() == original
    assert stat.S_IMODE(target.stat().st_mode) == original_mode
    assert "AI_API_KEY" not in os.environ


def test_main_startup_hardens_env_before_loading_credentials(tmp_path):
    home = tmp_path / "main-home"
    home.mkdir()
    env_path = home / ".env"
    env_path.write_text("AI_API_KEY=main-preserved-secret\n", encoding="utf-8")
    os.chmod(env_path, 0o644)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(paths._PACKAGE_DIR.parent)
    env["ZHIJI_HOME"] = str(home)
    env.pop("AI_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEEPSEEK_API_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, os, stat; "
                "import zhiji_backend.main; "
                "print(json.dumps({'key': os.environ.get('AI_API_KEY'), "
                "'mode': stat.S_IMODE(os.stat(os.environ['ZHIJI_HOME'] + '/.env').st_mode)}))"
            ),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"key": "main-preserved-secret", "mode": 0o600}


def test_main_and_cli_do_not_load_dotenv_before_hardening():
    root = paths._PACKAGE_DIR
    main_source = (root / "main.py").read_text(encoding="utf-8")
    cli_source = (root / "cli.py").read_text(encoding="utf-8")

    assert "load_dotenv(" not in main_source
    assert "load_dotenv(" not in cli_source
    assert "load_hardened_env(" in main_source
    assert "load_hardened_env(" in cli_source
