import argparse
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import cli, main
from zhiji_backend.routes import dashboard_routes
from zhiji_backend.main import app


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
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    trusted = _middleware_options(TrustedHostMiddleware)
    cors = _middleware_options(CORSMiddleware)

    assert trusted["allowed_hosts"] == ["localhost", "127.0.0.1", "[::1]", "testserver"]
    assert cors["allow_origins"] == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:9120",
        "http://127.0.0.1:9120",
        "tauri://localhost",
        "https://tauri.localhost",
    ]
    assert cors["allow_methods"] == ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    assert cors["allow_headers"] == ["Authorization", "Content-Type", "X-API-Key"]


def test_host_and_cors_environment_values_replace_defaults(monkeypatch):
    monkeypatch.setenv("KI_ALLOWED_HOSTS", "ki.example, 10.8.0.105")
    monkeypatch.setenv("KI_CORS_ORIGINS", "https://ki.example, http://10.8.0.105:5173")

    assert main._allowed_hosts() == ["ki.example", "10.8.0.105"]
    assert main._cors_origins() == ["https://ki.example", "http://10.8.0.105:5173"]


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


def test_serve_parser_defaults_to_loopback(monkeypatch):
    captured = {}

    def fake_serve(args: argparse.Namespace):
        captured["host"] = args.host

    monkeypatch.setattr("zhiji_backend.cli.cmd_serve", fake_serve)
    monkeypatch.setattr(sys, "argv", ["zhiji", "serve"])

    from zhiji_backend.cli import main as cli_main

    cli_main()

    assert captured["host"] == "127.0.0.1"
