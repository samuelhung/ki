import argparse
import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import cli, main
from zhiji_backend.main import app
from zhiji_backend.routes import dashboard_routes


def _middleware_options(middleware_class):
    for middleware in app.user_middleware:
        if middleware.cls is middleware_class:
            return middleware.kwargs
    raise AssertionError(f"{middleware_class.__name__} is not configured")


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({}, 401),
        ({"Authorization": "Bearer secret-token"}, 200),
        ({"Authorization": "Bearer wrong-token"}, 401),
        ({"X-API-Key": "secret-token"}, 200),
        ({"X-API-Key": "wrong-token"}, 401),
        ({"Cookie": "ki_session=retired-cookie"}, 401),
    ],
)
def test_remote_auth_accepts_only_matching_bearer_or_api_key(monkeypatch, headers, expected_status):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/dashboard/summary", headers=headers)

    assert response.status_code == expected_status


def test_allowed_cross_origin_auth_failure_includes_cors_headers(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get(
        "/api/dashboard/summary",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["vary"] == "Origin"


def test_remote_auth_uses_constant_time_comparison(monkeypatch):
    calls = []

    def compare_digest(candidate, expected):
        calls.append((candidate, expected))
        return candidate == expected

    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    monkeypatch.setattr(main.hmac, "compare_digest", compare_digest)
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get(
        "/api/dashboard/summary",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert calls == [("secret-token", "secret-token")]


def test_loopback_protected_requests_remain_passwordless():
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200


def test_public_health_is_exact_and_remote_passwordless():
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_detailed_health_is_protected_and_preserves_diagnostic_shape(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    denied = client.get("/api/system/health")
    response = client.get(
        "/api/system/health",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert denied.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "knowledge-intelligence"
    assert {"ok", "service", "version", "uptime_sec", "database"} == set(payload)
    assert {"ok", "size_mb", "event_count", "error"} == set(payload["database"])


def test_detailed_health_does_not_expose_raw_database_errors(monkeypatch):
    def fail_connect():
        raise RuntimeError("password=super-secret database path=/private/data")

    monkeypatch.setattr(dashboard_routes, "connect", fail_connect)
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get("/api/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["database"]["error"] == "database unavailable"
    assert "super-secret" not in response.text


def test_trusted_hosts_and_cors_are_narrow_and_have_desktop_defaults():
    from fastapi.middleware.cors import CORSMiddleware

    trusted = _middleware_options(main.TrustedHostMiddleware)
    cors = _middleware_options(CORSMiddleware)

    assert trusted["allowed_hosts"] == ["localhost", "127.0.0.1", "::1", "testserver"]
    assert cors["allow_origins"] == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:9120",
        "http://127.0.0.1:9120",
        "tauri://localhost",
        "https://tauri.localhost",
    ]
    assert cors["allow_methods"] == [
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]
    assert cors["allow_headers"] == [
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "Range",
        "If-Range",
        "If-None-Match",
        "If-Modified-Since",
        "If-Unmodified-Since",
    ]
    assert cors["expose_headers"] == [
        "Accept-Ranges",
        "Content-Length",
        "Content-Range",
        "Content-Type",
        "ETag",
        "Last-Modified",
    ]


def test_middleware_order_keeps_cors_outside_auth_and_host_validation():
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware

    assert [middleware.cls for middleware in app.user_middleware] == [
        CORSMiddleware,
        BaseHTTPMiddleware,
        BaseHTTPMiddleware,
        main.ProtectedPathMiddleware,
        main.TrustedHostMiddleware,
    ]
    assert [
        middleware.kwargs.get("dispatch")
        for middleware in app.user_middleware[1:3]
    ] == [main.spa_fallback, main.api_auth]


def test_allowed_origin_head_preflight_accepts_authorization_header():
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.options(
        "/ingest/videos/evt-1.mp4",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "HEAD",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "HEAD" in response.headers["access-control-allow-methods"].split(", ")
    assert "Authorization" in response.headers["access-control-allow-headers"]


def test_trusted_host_accepts_ipv6_loopback_with_port():
    client = TestClient(app, client=("::1", 50000))

    response = client.get("/api/health", headers={"Host": "[::1]:9120"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    "host_header",
    [
        "[::1].evil.example",
        "[::1]evil.example",
        "[::1]:9120.evil",
        "[::1]:not-a-port",
        "[::1]:",
    ],
)
def test_trusted_host_rejects_malformed_ipv6_suffix(host_header):
    client = TestClient(app, client=("::1", 50000))

    response = client.get("/api/health", headers={"Host": host_header})

    assert response.status_code == 400


def test_host_and_cors_environment_values_replace_defaults(monkeypatch):
    monkeypatch.setenv("KI_ALLOWED_HOSTS", "ki.example, 10.8.0.105")
    monkeypatch.setenv("KI_CORS_ORIGINS", "https://ki.example, http://10.8.0.105:5173")

    assert main._allowed_hosts() == ["ki.example", "10.8.0.105"]
    assert main._cors_origins() == ["https://ki.example", "http://10.8.0.105:5173"]


def test_ingest_artifact_route_serves_allowlisted_regular_file_with_range(
    tmp_path, monkeypatch
):
    ingest_root = tmp_path / "ingest"
    videos = ingest_root / "videos"
    videos.mkdir(parents=True)
    (videos / "evt-1.mp4").write_bytes(b"0123456789")
    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    client = TestClient(app)

    response = client.get(
        "/ingest/videos/evt-1.mp4", headers={"Range": "bytes=2-5"}
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["accept-ranges"] == "bytes"


def test_ingest_artifact_head_matches_get_headers_without_body(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    documents = ingest_root / "documents"
    documents.mkdir(parents=True)
    (documents / "evt-1.pdf").write_bytes(b"0123456789")
    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    client = TestClient(app)

    get_response = client.get("/ingest/documents/evt-1.pdf")
    head_response = client.head("/ingest/documents/evt-1.pdf")

    assert get_response.status_code == 200
    assert head_response.status_code == 200
    assert head_response.content == b""
    for header in (
        "accept-ranges",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
    ):
        assert head_response.headers[header] == get_response.headers[header]


def test_remote_ingest_artifact_head_uses_existing_token_auth(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    videos = ingest_root / "videos"
    videos.mkdir(parents=True)
    (videos / "evt-1.mp4").write_bytes(b"video")
    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    denied = client.head("/ingest/videos/evt-1.mp4")
    allowed = client.head(
        "/ingest/videos/evt-1.mp4",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.content == b""
    assert allowed.headers["content-length"] == "5"


@pytest.mark.parametrize("kind", ["pending", "internal", "concepts"])
def test_ingest_artifact_route_denies_non_public_directories(tmp_path, monkeypatch, kind):
    ingest_root = tmp_path / "ingest"
    directory = ingest_root / kind
    directory.mkdir(parents=True)
    (directory / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    client = TestClient(app)

    response = client.get(f"/ingest/{kind}/secret.txt")

    assert response.status_code == 404
    assert b"secret" not in response.content


def test_ingest_artifact_route_rejects_traversal_and_symlink_escape(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    documents = ingest_root / "documents"
    documents.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-secret", encoding="utf-8")
    (documents / "linked.txt").symlink_to(outside)
    monkeypatch.setattr(main, "INGEST_ROOT", ingest_root)
    client = TestClient(app)

    traversal = client.get("/ingest/documents/..%2F..%2Foutside.txt")
    symlink = client.get("/ingest/documents/linked.txt")

    assert traversal.status_code == 422
    assert symlink.status_code == 404
    assert b"outside-secret" not in traversal.content + symlink.content


def test_release_route_rejects_percent_encoded_traversal_and_symlink(tmp_path, monkeypatch):
    releases = tmp_path / "releases"
    releases.mkdir()
    outside = tmp_path / "outside.dmg"
    outside.write_bytes(b"outside-release")
    (releases / "linked.dmg").symlink_to(outside)
    monkeypatch.setattr(main, "RELEASES_DIR", releases)
    client = TestClient(app)

    traversal = client.get("/releases/..%2Foutside.dmg")
    symlink = client.get("/releases/linked.dmg")

    assert traversal.status_code == 422
    assert symlink.status_code == 404
    assert b"outside-release" not in traversal.content + symlink.content


def test_protected_spa_fallback_never_serves_frontend_index(tmp_path, monkeypatch):
    from starlette.requests import Request
    from starlette.responses import Response

    from zhiji_backend import main

    frontend_dist = tmp_path / "frontend"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("frontend-index", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", frontend_dist)
    monkeypatch.setattr(main, "_HAS_FRONTEND", True)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/ingest/private/missing.txt",
            "raw_path": b"/ingest/private/missing.txt",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.protected_path = True

    async def missing_response(_request):
        return Response(status_code=404)

    async def exercise():
        return await main.spa_fallback(request, missing_response)

    response = asyncio.run(exercise())

    assert response.status_code == 404
    assert response.headers.get("cache-control") is None


def test_registered_auth_resolves_main_helper_aliases_at_request_time(monkeypatch):
    monkeypatch.setattr(main, "_requires_token_for_request", lambda *_args: True)
    monkeypatch.setattr(main, "_api_token", lambda: "runtime-token")
    monkeypatch.setattr(main, "_request_token", lambda _request: "runtime-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    allowed = client.get("/api/dashboard/summary")
    monkeypatch.setattr(main, "_request_token", lambda _request: "wrong-token")
    denied = client.get("/api/dashboard/summary")

    assert allowed.status_code == 200
    assert denied.status_code == 401


def test_registered_auth_uses_patched_main_protected_path_helper(monkeypatch):
    monkeypatch.delenv("KI_API_TOKEN", raising=False)
    monkeypatch.setattr(main, "_is_protected_path", lambda _path: True)
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/facade-protected-missing")

    assert response.status_code == 401


def test_registered_auth_uses_patched_main_loopback_helper(monkeypatch):
    monkeypatch.delenv("KI_API_TOKEN", raising=False)
    monkeypatch.setattr(main, "_is_loopback_host", lambda _host: False)
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 401


def test_registered_auth_preserves_patched_main_requires_token_override(monkeypatch):
    monkeypatch.setattr(main, "_requires_token_for_request", lambda *_args: False)
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200


def test_middleware_pipeline_resolves_one_dependency_snapshot_per_request(
    monkeypatch,
):
    from zhiji_backend import api_middleware

    calls = []
    real_current_dependencies = api_middleware._current_dependencies

    def current_dependencies():
        calls.append("resolve")
        return real_current_dependencies()

    monkeypatch.setattr(api_middleware, "_current_dependencies", current_dependencies)

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert calls == ["resolve"]


def test_facade_dependency_snapshot_captures_api_token_once(monkeypatch):
    from zhiji_backend import api_middleware

    values = ["first-token", "second-token"]
    calls = []

    def api_token():
        calls.append("token")
        return values.pop(0)

    monkeypatch.setattr(main, "_api_token", api_token)
    snapshot = api_middleware._DEFAULT_FACTORY_REGISTRATION.factory()

    assert snapshot.api_token() == "first-token"
    assert snapshot.api_token() == "first-token"
    assert calls == ["token"]


def test_api_middleware_reload_keeps_old_app_dependencies_valid(tmp_path):
    script = """
import importlib
import json
from fastapi.testclient import TestClient
from zhiji_backend import api_middleware, main

old_app = main.app
importlib.reload(api_middleware)
old_response = TestClient(old_app).get('/api/health')
importlib.reload(main)
new_response = TestClient(main.app).get('/api/health')
registration = api_middleware._DEFAULT_FACTORY_REGISTRATION
print(json.dumps({
    'old_status': old_response.status_code,
    'new_status': new_response.status_code,
    'factory_type': type(registration.factory).__name__,
    'api_auth_identity': main.api_auth is api_middleware.api_auth,
}))
"""
    environment = dict(
        os.environ,
        PYTHONPATH=f"{ROOT / 'src'}:{ROOT}",
        ZHIJI_HOME=str(tmp_path / "home"),
    )

    completed = __import__("subprocess").run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert __import__("json").loads(completed.stdout) == {
        "old_status": 200,
        "new_status": 200,
        "factory_type": "FacadeDependencyFactory",
        "api_auth_identity": True,
    }


def test_factory_registration_change_survives_api_middleware_reload(tmp_path):
    script = """
import importlib
import json
from zhiji_backend import api_middleware

api_middleware._DEFAULT_FACTORY_REGISTRATION = None

def factory():
    return None

first = api_middleware.register_default_dependency_factory(factory, owner='test')

def replacement():
    return None

replacement.__qualname__ = factory.__qualname__
change = api_middleware.register_default_dependency_factory(replacement, owner='test')
installed = change.installed
previous = change.previous
importlib.reload(api_middleware)
rolled_back = api_middleware.rollback_default_dependency_factory(change)
print(json.dumps({
    'changed': first.changed and change.changed,
    'installed_before_reload': installed.factory is replacement,
    'rolled_back': rolled_back,
    'previous_restored': api_middleware._DEFAULT_FACTORY_REGISTRATION is previous,
}))
"""
    environment = dict(
        os.environ,
        PYTHONPATH=f"{ROOT / 'src'}:{ROOT}",
        ZHIJI_HOME=str(tmp_path / "home"),
    )

    completed = __import__("subprocess").run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert __import__("json").loads(completed.stdout) == {
        "changed": True,
        "installed_before_reload": True,
        "rolled_back": True,
        "previous_restored": True,
    }


def test_factory_registration_rollback_rejects_malformed_artifact(monkeypatch):
    from types import SimpleNamespace

    from zhiji_backend import api_middleware

    installed = api_middleware._DEFAULT_FACTORY_REGISTRATION
    malformed = SimpleNamespace(
        previous=object(),
        installed=installed,
        changed=True,
    )

    with pytest.raises(TypeError, match="DefaultFactoryRegistrationChange"):
        api_middleware.rollback_default_dependency_factory(malformed)

    assert api_middleware._DEFAULT_FACTORY_REGISTRATION is installed


@pytest.mark.parametrize(
    "mutation",
    [
        lambda dependencies: vars(dependencies).pop("api_token"),
        lambda dependencies: setattr(dependencies, "request_token", "not-callable"),
        lambda dependencies: setattr(dependencies, "has_frontend", "yes"),
        lambda dependencies: setattr(dependencies, "frontend_dist", object()),
    ],
)
def test_malformed_structural_middleware_dependencies_are_rejected(
    monkeypatch, mutation
):
    from types import SimpleNamespace

    from zhiji_backend import api_middleware

    dependencies = SimpleNamespace(
        api_token=lambda: "",
        request_token=lambda _request: "",
        requires_token_for_request=lambda _path, _host: False,
        is_protected_path=lambda _path: False,
        is_loopback_host=lambda _host: True,
        compare_digest=lambda left, right: left == right,
        has_frontend=True,
        frontend_dist=Path("frontend"),
    )
    mutation(dependencies)
    monkeypatch.setattr(
        api_middleware,
        "_DEFAULT_FACTORY_REGISTRATION",
        SimpleNamespace(factory=lambda: dependencies),
    )

    with pytest.raises(TypeError, match="default dependency factory"):
        api_middleware._current_dependencies()


def _dependency_snapshot(api_middleware, frontend_dist: Path):
    return api_middleware.MiddlewareDependencies(
        api_token=lambda: "",
        request_token=lambda _request: "",
        requires_token_for_request=lambda _path, _host: False,
        is_protected_path=lambda _path: False,
        is_loopback_host=lambda _host: True,
        compare_digest=lambda left, right: left == right,
        has_frontend=True,
        frontend_dist=frontend_dist,
    )


def _reload_factory(snapshot):
    def factory():
        return snapshot

    factory.__qualname__ = "test_reload_dependency_factory"
    return factory


def test_dependency_resolution_waits_for_factory_transaction_commit(
    tmp_path, monkeypatch
):
    from zhiji_backend import api_middleware

    base = _dependency_snapshot(api_middleware, tmp_path / "base")
    candidate = _dependency_snapshot(api_middleware, tmp_path / "candidate")
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_LOCK", threading.RLock())
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_REGISTRATION", None)
    api_middleware.register_default_dependency_factory(_reload_factory(base), owner="test")
    transaction_open = threading.Event()
    finish_transaction = threading.Event()
    resolver_started = threading.Event()
    resolved = threading.Event()
    observed = []

    def assemble():
        with api_middleware.default_dependency_factory_transaction(
            _reload_factory(candidate), owner="test"
        ):
            transaction_open.set()
            assert finish_transaction.wait(2)

    def resolve():
        resolver_started.set()
        observed.append(api_middleware._current_dependencies())
        resolved.set()

    assembly_thread = threading.Thread(target=assemble)
    assembly_thread.start()
    assert transaction_open.wait(2)
    resolver_thread = threading.Thread(target=resolve)
    resolver_thread.start()
    assert resolver_started.wait(2)
    assert not resolved.wait(0.1)

    finish_transaction.set()
    assembly_thread.join(2)
    resolver_thread.join(2)

    assert observed == [candidate]


def test_dependency_resolution_waits_for_factory_transaction_rollback(
    tmp_path, monkeypatch
):
    from zhiji_backend import api_middleware

    base = _dependency_snapshot(api_middleware, tmp_path / "base")
    candidate = _dependency_snapshot(api_middleware, tmp_path / "candidate")
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_LOCK", threading.RLock())
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_REGISTRATION", None)
    api_middleware.register_default_dependency_factory(_reload_factory(base), owner="test")
    transaction_open = threading.Event()
    fail_transaction = threading.Event()
    resolved = threading.Event()
    observed = []
    failures = []

    def assemble():
        try:
            with api_middleware.default_dependency_factory_transaction(
                _reload_factory(candidate), owner="test"
            ):
                transaction_open.set()
                assert fail_transaction.wait(2)
                raise RuntimeError("assembly failed")
        except RuntimeError as error:
            failures.append(str(error))

    def resolve():
        observed.append(api_middleware._current_dependencies())
        resolved.set()

    assembly_thread = threading.Thread(target=assemble)
    assembly_thread.start()
    assert transaction_open.wait(2)
    resolver_thread = threading.Thread(target=resolve)
    resolver_thread.start()
    assert not resolved.wait(0.1)

    fail_transaction.set()
    assembly_thread.join(2)
    resolver_thread.join(2)

    assert failures == ["assembly failed"]
    assert observed == [base]


def test_overlapping_failed_factory_transactions_restore_committed_base(
    tmp_path, monkeypatch
):
    from zhiji_backend import api_middleware

    base = _dependency_snapshot(api_middleware, tmp_path / "base")
    first = _dependency_snapshot(api_middleware, tmp_path / "first")
    second = _dependency_snapshot(api_middleware, tmp_path / "second")
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_LOCK", threading.RLock())
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_REGISTRATION", None)
    api_middleware.register_default_dependency_factory(_reload_factory(base), owner="test")
    first_open = threading.Event()
    fail_first = threading.Event()
    second_started = threading.Event()
    second_open = threading.Event()
    fail_second = threading.Event()

    def fail_transaction(snapshot, opened, release):
        try:
            with api_middleware.default_dependency_factory_transaction(
                _reload_factory(snapshot), owner="test"
            ):
                opened.set()
                assert release.wait(2)
                raise RuntimeError("assembly failed")
        except RuntimeError:
            pass

    first_thread = threading.Thread(
        target=fail_transaction, args=(first, first_open, fail_first)
    )
    first_thread.start()
    assert first_open.wait(2)

    def run_second():
        second_started.set()
        fail_transaction(second, second_open, fail_second)

    second_thread = threading.Thread(target=run_second)
    second_thread.start()
    assert second_started.wait(2)
    assert not second_open.wait(0.1)
    fail_first.set()
    assert second_open.wait(2)
    fail_second.set()
    first_thread.join(2)
    second_thread.join(2)

    assert api_middleware._current_dependencies() is base


def test_registered_protected_path_resolves_main_alias_at_request_time(
    tmp_path, monkeypatch
):
    frontend_dist = tmp_path / "frontend"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("runtime-index", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", frontend_dist)
    monkeypatch.setattr(main, "_HAS_FRONTEND", True)
    monkeypatch.setattr(main, "_is_protected_path", lambda _path: True)

    response = TestClient(app).get("/runtime-protected-missing")

    assert response.status_code == 404
    assert b"runtime-index" not in response.content


def test_spa_fallback_pins_one_main_dependency_snapshot_per_request(
    tmp_path, monkeypatch
):
    from starlette.requests import Request
    from starlette.responses import Response

    first_dist = tmp_path / "first"
    second_dist = tmp_path / "second"
    first_dist.mkdir()
    second_dist.mkdir()
    (first_dist / "index.html").write_text("first-index", encoding="utf-8")
    (second_dist / "index.html").write_text("second-index", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", first_dist)
    monkeypatch.setattr(main, "_HAS_FRONTEND", True)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/snapshot",
            "raw_path": b"/snapshot",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    async def missing_response(_request):
        monkeypatch.setattr(main, "FRONTEND_DIST", second_dist)
        return Response(status_code=404)

    response = asyncio.run(main.spa_fallback(request, missing_response))

    assert Path(response.path) == first_dist / "index.html"


def test_direct_api_middleware_fallback_checks_frontend_at_request_time(
    tmp_path, monkeypatch
):
    from starlette.requests import Request
    from starlette.responses import Response

    from zhiji_backend import api_middleware

    frontend_dist = tmp_path / "frontend"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("direct-index", encoding="utf-8")
    monkeypatch.setattr(api_middleware, "_DEFAULT_FACTORY_REGISTRATION", None)
    monkeypatch.setattr(api_middleware, "FRONTEND_DIST", frontend_dist)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/direct",
            "raw_path": b"/direct",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    async def missing_response(_request):
        return Response(status_code=404)

    response = asyncio.run(api_middleware.spa_fallback(request, missing_response))

    assert Path(response.path) == frontend_dist / "index.html"
    assert not hasattr(api_middleware, "_HAS_FRONTEND")


def test_static_delivery_closes_opened_artifact_when_response_creation_fails():
    from fastapi import HTTPException

    from zhiji_backend import static_delivery

    class OpenedSpy:
        closed = False

        def close(self):
            self.closed = True

    opened = OpenedSpy()

    async def exercise():
        await static_delivery.serve_ingest_artifact(
            "videos",
            "event.mp4",
            public_ingest_artifacts={"videos"},
            ingest_root=object(),
            safe_identifier=lambda value: value,
            open_regular_under=lambda *_args: opened,
            pinned_file_response=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("response failed")
            ),
            artifact_open_error=OSError,
            http_exception=HTTPException,
        )

    with pytest.raises(RuntimeError, match="response failed"):
        asyncio.run(exercise())

    assert opened.closed is True


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_serve_hosts_do_not_require_api_token(monkeypatch, host):
    monkeypatch.delenv("KI_API_TOKEN", raising=False)

    cli._validate_serve_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.8.0.105", "ki.example"])
def test_non_loopback_serve_hosts_require_api_token(monkeypatch, host):
    monkeypatch.delenv("KI_API_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="KI_API_TOKEN"):
        cli._validate_serve_host(host)


def test_non_loopback_serve_host_is_allowed_with_api_token(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")

    cli._validate_serve_host("0.0.0.0")


def test_non_loopback_serve_loads_token_from_selected_data_dir(tmp_path, monkeypatch):
    import uvicorn

    data_dir = tmp_path / "selected-home"
    data_dir.mkdir()
    (data_dir / ".env").write_text("KI_API_TOKEN=persisted-token\n", encoding="utf-8")
    calls = []
    monkeypatch.delenv("KI_API_TOKEN", raising=False)
    monkeypatch.delenv("ZHIJI_HOME", raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    cli.cmd_serve(argparse.Namespace(data_dir=str(data_dir), host="0.0.0.0", port=9120))

    assert os.environ["ZHIJI_HOME"] == str(data_dir)
    assert os.environ["KI_API_TOKEN"] == "persisted-token"
    assert calls[0][1]["host"] == "0.0.0.0"


def test_serve_parser_defaults_to_loopback(monkeypatch):
    captured = {}

    def fake_serve(args: argparse.Namespace):
        captured["host"] = args.host

    monkeypatch.setattr("zhiji_backend.cli.cmd_serve", fake_serve)
    monkeypatch.setattr(sys, "argv", ["zhiji", "serve"])

    from zhiji_backend.cli import main as cli_main

    cli_main()

    assert captured["host"] == "127.0.0.1"


def test_relative_explicit_env_file_is_rejected(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["ZHIJI_HOME"] = str(tmp_path)
    env["KI_ENV_FILE"] = "relative.env"

    result = subprocess.run(
        [sys.executable, "-c", "import zhiji_backend.paths"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "KI_ENV_FILE must be absolute" in result.stderr
