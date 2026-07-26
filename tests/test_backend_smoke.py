import asyncio
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.db import connect, get_db_path, init_db
from zhiji_backend.main import _requires_token_for_request, app


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_dashboard_bootstrap_summary_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    client = TestClient(app)

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert {"sources_enabled", "today_new", "ingest_total", "brainstorm_total"} == set(payload)
    assert payload["today_new"] == 0
    assert payload["ingest_total"] == 0
    assert payload["brainstorm_total"] == 0


def test_series_list_resolves_members_before_connection_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('manual', '手动', 'manual', '', '认知', 1)"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, status)
               VALUES ('evt-series-1', 'manual', '专题成员一', 'https://example.com/1', '认知', 'completed')"""
        )
        conn.execute(
            """INSERT INTO series (id, name, description, member_ids, status)
               VALUES ('series-1', '测试专题', '用于连接生命周期回归', '["evt-series-1"]', 'published')"""
        )
        conn.execute(
            "UPDATE series SET intro = '大段导言', summary = '大段总结', paper = '大段分析' "
            "WHERE id = 'series-1'"
        )

    client = TestClient(app)

    response = client.get("/api/ingest/series")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["members"] == [{"id": "evt-series-1", "title": "专题成员一"}]
    assert "intro" not in payload["items"][0]
    assert "summary" not in payload["items"][0]
    assert "paper" not in payload["items"][0]


def test_init_db_creates_sqlite_file(tmp_path, monkeypatch):
    db_path = tmp_path / "intelligence.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))

    init_db()

    assert get_db_path() == db_path
    assert db_path.exists()


def test_remote_requests_require_token_when_no_token_configured():
    assert _requires_token_for_request("/api/sources", "10.8.0.2") is True
    assert _requires_token_for_request("/ingest/documents/a.pdf", "10.8.0.2") is True
    assert _requires_token_for_request("/releases/zhiji_1.3.7.dmg", "10.8.0.2") is True


def test_public_and_protected_path_classification_is_exact():
    from zhiji_backend import main

    assert {
        path: main._is_protected_path(path)
        for path in (
            "/api",
            "/api/health",
            "/ingest/videos/a.mp4",
            "/releases/appcast.xml",
            "/",
            "/assets/index.js",
        )
    } == {
        "/api": True,
        "/api/health": True,
        "/ingest/videos/a.mp4": True,
        "/releases/appcast.xml": True,
        "/": False,
        "/assets/index.js": False,
    }


def test_local_requests_do_not_require_token_by_default():
    assert _requires_token_for_request("/api/sources", "127.0.0.1") is False
    assert _requires_token_for_request("/api/sources", "::1") is False
    assert _requires_token_for_request("/ingest/documents/a.pdf", "localhost") is False


def test_local_requests_do_not_require_token_when_token_configured(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get("/api/sources")

    assert response.status_code != 401


def test_remote_api_request_without_token_returns_401():
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/sources")

    assert response.status_code == 401


def test_remote_api_request_accepts_runtime_token(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/sources", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code != 401


def test_releases_only_serves_top_level_dmg_or_appcast(tmp_path, monkeypatch):
    from zhiji_backend import main

    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()
    (releases_dir / "zhiji_1.3.7.dmg").write_bytes(b"dmg")
    (releases_dir / "secret.txt").write_text("secret", encoding="utf-8")
    nested_dir = releases_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "zhiji_1.3.7.dmg").write_bytes(b"nested")
    monkeypatch.setattr(main, "RELEASES_DIR", releases_dir)

    client = TestClient(app)

    assert client.get("/releases/zhiji_1.3.7.dmg").status_code == 200
    assert client.get("/releases/appcast.xml").status_code == 404
    assert client.get("/releases/secret.txt").status_code == 404
    assert client.get("/releases/nested/zhiji_1.3.7.dmg").status_code == 404


def test_extracted_lifespan_preserves_cancellation_and_cleanup_order():
    from zhiji_backend import app_lifecycle

    calls = []

    class LoggerSpy:
        def info(self, message):
            calls.append(("info", message))

        def error(self, message):
            calls.append(("error", message))

    def record(name, result=None):
        def operation(*_args):
            calls.append(name)
            return result

        return operation

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            async with app_lifecycle.lifespan(
                object(),
                logger=LoggerSpy(),
                ensure_migrations=record("migrate"),
                get_db_path=lambda: calls.append("db-path") or Path("db.sqlite"),
                load_config=record("config"),
                init_db=record("db"),
                seed_default_sources=record("seed"),
                start_usage_writer=record("usage-start"),
                stop_usage_writer=record("usage-stop"),
                start_worker=record("worker-start"),
                stop_worker=record("worker-stop", True),
            ):
                calls.append("running")
                raise asyncio.CancelledError

    asyncio.run(exercise())

    assert calls == [
        ("info", "KI server starting — init DB + worker"),
        "db-path",
        "migrate",
        "config",
        "db",
        "seed",
        "usage-start",
        "worker-start",
        ("info", "KI server ready"),
        "running",
        ("info", "KI server shutting down"),
        "worker-stop",
        "usage-stop",
    ]


def test_application_bootstrap_prepares_environment_before_importing_dependencies():
    from zhiji_backend import main

    calls = []
    dependencies = object()

    result = main._bootstrap_application(
        prepare_runtime=lambda: calls.append("prepare-runtime"),
        load_dependencies=lambda: calls.append("load-dependencies") or dependencies,
    )

    assert result is dependencies
    assert calls == ["prepare-runtime", "load-dependencies"]


def test_prepare_runtime_installs_tagged_handlers_only_once(tmp_path, monkeypatch):
    from zhiji_backend import main

    class HandlerSpy:
        def setLevel(self, _level):
            pass

        def setFormatter(self, _formatter):
            pass

        def close(self):
            pass

    class RootSpy:
        def __init__(self):
            self.handlers = []
            self.level = 0

        def setLevel(self, level):
            self.level = level

        def addHandler(self, handler):
            self.handlers.append(handler)

        def removeHandler(self, handler):
            self.handlers.remove(handler)

    root = RootSpy()
    monkeypatch.setattr(main, "ensure_data_dirs", lambda: None)
    monkeypatch.setattr(main, "load_hardened_env", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "LOG_DIR", tmp_path)
    monkeypatch.setattr(main, "_root_logger", lambda: root)
    monkeypatch.setattr(main, "_create_console_handler", HandlerSpy)
    monkeypatch.setattr(main, "_create_file_handler", lambda: HandlerSpy())

    first = main._prepare_runtime()
    second = main._prepare_runtime()

    assert first.handlers == tuple(root.handlers)
    assert second.handlers == ()
    assert [handler._zhiji_handler_role for handler in root.handlers] == [
        "console",
        "file",
    ]


def test_bootstrap_cleans_only_handlers_installed_by_each_failed_attempt(
    monkeypatch,
):
    from zhiji_backend import main

    class HandlerSpy:
        def __init__(self, name):
            self.name = name
            self.closed = False

        def close(self):
            self.closed = True

    class RootSpy:
        def __init__(self):
            self.handlers = [HandlerSpy("user")]

        def removeHandler(self, handler):
            self.handlers.remove(handler)

    root = RootSpy()
    attempts = []
    monkeypatch.setattr(main, "_root_logger", lambda: root)

    def prepare():
        handlers = (
            HandlerSpy(f"ki-{len(attempts)}-console"),
            HandlerSpy(f"ki-{len(attempts)}-file"),
        )
        root.handlers.extend(handlers)
        attempts.append(handlers)
        return handlers

    def fail_load():
        raise ImportError("dependency load failed")

    for _attempt in range(2):
        with pytest.raises(ImportError, match="dependency load failed"):
            main._bootstrap_application(
                prepare_runtime=prepare,
                load_dependencies=fail_load,
            )
        assert [handler.name for handler in root.handlers] == ["user"]

    assert all(handler.closed for attempt in attempts for handler in attempt)


def test_bootstrap_cleanup_failure_preserves_dependency_import_error(monkeypatch):
    from zhiji_backend import main

    class HandlerSpy:
        def close(self):
            raise RuntimeError("close failed")

    class RootSpy:
        handlers = []

        def removeHandler(self, _handler):
            raise RuntimeError("remove failed")

    monkeypatch.setattr(main, "_root_logger", lambda: RootSpy())

    with pytest.raises(ImportError, match="original import failure"):
        main._bootstrap_application(
            prepare_runtime=lambda: (HandlerSpy(),),
            load_dependencies=lambda: (_ for _ in ()).throw(
                ImportError("original import failure")
            ),
        )


def test_main_reload_reuses_ki_handlers_and_does_not_duplicate_file_records(tmp_path):
    script = """
import importlib
import json
import logging
from zhiji_backend import main

root = logging.getLogger()
user_handler = logging.NullHandler()
root.addHandler(user_handler)
tagged_before = [h for h in root.handlers if getattr(h, '_zhiji_handler_owner', None) == 'zhiji']
identities_before = [id(h) for h in tagged_before]
importlib.reload(main)
importlib.reload(main)
tagged_after = [h for h in root.handlers if getattr(h, '_zhiji_handler_owner', None) == 'zhiji']
logging.getLogger('reload-test').warning('reload-record-marker')
for handler in tagged_after:
    handler.flush()
log_text = (main.LOG_DIR / 'ki.log').read_text(encoding='utf-8')
print(json.dumps({
    'before': identities_before,
    'after': [id(h) for h in tagged_after],
    'marker_count': log_text.count('reload-record-marker'),
    'user_handler_preserved': user_handler in root.handlers,
}))
"""
    environment = dict(
        os.environ,
        PYTHONPATH=str(ROOT / "src"),
        ZHIJI_HOME=str(tmp_path / "home"),
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["after"] == result["before"]
    assert len(result["after"]) == 2
    assert result["marker_count"] == 1
    assert result["user_handler_preserved"] is True


def test_failed_static_mount_rolls_back_complete_import_bootstrap(tmp_path):
    script = """
import importlib
import json
import logging
import sys
from zhiji_backend import api_middleware, static_delivery

root = logging.getLogger()
root.setLevel(logging.ERROR)
for name, level in (
    ('httpx', logging.INFO),
    ('httpcore', logging.ERROR),
    ('urllib3', logging.CRITICAL),
):
    logging.getLogger(name).setLevel(level)
levels_before = {
    name: logging.getLogger(name).level
    for name in ('', 'httpx', 'httpcore', 'urllib3')
}
tagged_before = [
    id(handler)
    for handler in root.handlers
    if getattr(handler, '_zhiji_handler_owner', None) == 'zhiji'
]
registration_before = api_middleware._DEFAULT_FACTORY_REGISTRATION

def fail_mount(*_args, **_kwargs):
    raise RuntimeError('mount failed')

static_delivery.mount_frontend = fail_mount
try:
    importlib.import_module('zhiji_backend.main')
except RuntimeError as error:
    failure = str(error)
else:
    failure = ''

tagged_after = [
    id(handler)
    for handler in root.handlers
    if getattr(handler, '_zhiji_handler_owner', None) == 'zhiji'
]
levels_after = {
    name: logging.getLogger(name).level
    for name in ('', 'httpx', 'httpcore', 'urllib3')
}
print(json.dumps({
    'failure': failure,
    'module_present': 'zhiji_backend.main' in sys.modules,
    'tagged_before': tagged_before,
    'tagged_after': tagged_after,
    'registration_restored': (
        api_middleware._DEFAULT_FACTORY_REGISTRATION is registration_before
    ),
    'levels_restored': levels_after == levels_before,
}))
"""
    environment = dict(
        os.environ,
        PYTHONPATH=f"{ROOT / 'src'}:{ROOT}",
        ZHIJI_HOME=str(tmp_path / "home"),
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "failure": "mount failed",
        "module_present": False,
        "tagged_before": [],
        "tagged_after": [],
        "registration_restored": True,
        "levels_restored": True,
    }


def test_failed_static_mount_reload_preserves_prior_runtime_and_factory(tmp_path):
    script = """
import importlib
import json
import logging
from zhiji_backend import api_middleware, main

root = logging.getLogger()
root.setLevel(logging.ERROR)
for name, level in (
    ('httpx', logging.INFO),
    ('httpcore', logging.ERROR),
    ('urllib3', logging.CRITICAL),
):
    logging.getLogger(name).setLevel(level)
levels_before = {
    name: logging.getLogger(name).level
    for name in ('', 'httpx', 'httpcore', 'urllib3')
}
tagged_before = [
    id(handler)
    for handler in root.handlers
    if getattr(handler, '_zhiji_handler_owner', None) == 'zhiji'
]
registration_before = api_middleware._DEFAULT_FACTORY_REGISTRATION
main._HAS_FRONTEND = True
frontend_before = main._HAS_FRONTEND

def fail_mount(*_args, **_kwargs):
    raise RuntimeError('reload mount failed')

main.static_delivery.mount_frontend = fail_mount
try:
    importlib.reload(main)
except RuntimeError as error:
    failure = str(error)
else:
    failure = ''

tagged_after = [
    id(handler)
    for handler in root.handlers
    if getattr(handler, '_zhiji_handler_owner', None) == 'zhiji'
]
levels_after = {
    name: logging.getLogger(name).level
    for name in ('', 'httpx', 'httpcore', 'urllib3')
}
registration_after = api_middleware._DEFAULT_FACTORY_REGISTRATION
print(json.dumps({
    'failure': failure,
    'tagged_preserved': tagged_after == tagged_before,
    'registration_restored': registration_after is registration_before,
    'frontend_restored': main._HAS_FRONTEND is frontend_before,
    'factory_frontend_restored': (
        registration_after.factory().has_frontend is frontend_before
    ),
    'levels_restored': levels_after == levels_before,
}))
"""
    environment = dict(
        os.environ,
        PYTHONPATH=f"{ROOT / 'src'}:{ROOT}",
        ZHIJI_HOME=str(tmp_path / "home"),
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "failure": "reload mount failed",
        "tagged_preserved": True,
        "registration_restored": True,
        "frontend_restored": True,
        "factory_frontend_restored": True,
        "levels_restored": True,
    }


@pytest.mark.parametrize("failure_stage", ["prepare", "load"])
def test_failed_early_reload_preserves_completed_application_state(
    tmp_path, failure_stage
):
    script = f"""
import importlib
import json
from zhiji_backend import api_middleware, main, paths

app_before = main.app
lifespan_before = main.lifespan
registration_before = api_middleware._DEFAULT_FACTORY_REGISTRATION
main._HAS_FRONTEND = True

def fail(*_args, **_kwargs):
    raise RuntimeError('{failure_stage} failed')

if '{failure_stage}' == 'prepare':
    paths.ensure_data_dirs = fail
else:
    real_import_module = importlib.import_module
    def fail_dependency(name, package=None):
        if name == '.config_manager':
            return fail()
        return real_import_module(name, package)
    importlib.import_module = fail_dependency

try:
    importlib.reload(main)
except RuntimeError as error:
    failure = str(error)
else:
    failure = ''

registration_after = api_middleware._DEFAULT_FACTORY_REGISTRATION
print(json.dumps({{
    'failure': failure,
    'app_restored': main.app is app_before,
    'lifespan_restored': main.lifespan is lifespan_before,
    'registration_restored': registration_after is registration_before,
    'frontend_restored': main._HAS_FRONTEND is True,
    'factory_frontend_restored': registration_after.factory().has_frontend is True,
}}))
"""
    environment = dict(
        os.environ,
        PYTHONPATH=f"{ROOT / 'src'}:{ROOT}",
        ZHIJI_HOME=str(tmp_path / "home"),
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "failure": f"{failure_stage} failed",
        "app_restored": True,
        "lifespan_restored": True,
        "registration_restored": True,
        "frontend_restored": True,
        "factory_frontend_restored": True,
    }


@pytest.mark.parametrize(
    "failure_stage",
    ["registration", "fastapi", "middleware", "routes", "mkdir", "mount", "publish"],
)
def test_failed_application_assembly_restores_facade_and_registration(
    monkeypatch, failure_stage
):
    from zhiji_backend import api_middleware, main

    state_names = ("app", "_assembly", "_dependencies", "_HAS_FRONTEND", "api_auth")
    state_before = {name: getattr(main, name) for name in state_names}
    registration_before = api_middleware._DEFAULT_FACTORY_REGISTRATION

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"{failure_stage} failed")

    if failure_stage == "registration":

        @contextmanager
        def fail_registration(*_args, **_kwargs):
            fail()
            yield

        monkeypatch.setattr(
            api_middleware,
            "default_dependency_factory_transaction",
            fail_registration,
        )
    elif failure_stage == "fastapi":
        monkeypatch.setattr(main, "FastAPI", fail)
    elif failure_stage == "middleware":
        monkeypatch.setattr(main, "_add_middleware", fail)
    elif failure_stage == "routes":
        monkeypatch.setattr(main, "_add_routes", fail)
    elif failure_stage == "mkdir":

        class ReleasesDirFailure:
            def mkdir(self, **_kwargs):
                fail()

        monkeypatch.setattr(main, "RELEASES_DIR", ReleasesDirFailure())
    elif failure_stage == "mount":
        monkeypatch.setattr(main.static_delivery, "mount_frontend", fail)
    else:

        def fail_publish(_dependencies):
            main.api_auth = object()
            fail()

        monkeypatch.setattr(main, "_publish_dependencies", fail_publish)

    with pytest.raises(RuntimeError, match=rf"{failure_stage} failed"):
        main._assemble_application(main._dependencies)

    assert {name: getattr(main, name) for name in state_names} == state_before
    assert api_middleware._DEFAULT_FACTORY_REGISTRATION is registration_before


def test_router_manifest_drives_dependency_loading_and_inclusion_order():
    from zhiji_backend import main

    assert tuple(main._dependencies.routes) == main.ROUTE_NAMES
    included = [
        route.original_router
        for route in main.app.routes
        if type(route).__name__ == "_IncludedRouter"
    ]
    assert included == [getattr(main, f"{name}_router") for name in main.ROUTE_NAMES]


def test_missing_frontend_is_not_mounted(tmp_path):
    from zhiji_backend import static_delivery

    calls = []

    class AppSpy:
        def mount(self, *args, **kwargs):
            calls.append((args, kwargs))

    mounted = static_delivery.mount_frontend(
        AppSpy(),
        frontend_dist=tmp_path / "missing",
        static_files=lambda **_kwargs: pytest.fail("StaticFiles must not be created"),
    )

    assert mounted is False
    assert calls == []


def test_main_frontend_state_matches_the_single_frontend_mount():
    from zhiji_backend import main

    frontend_mounts = [
        route
        for route in main.app.routes
        if type(route).__name__ == "Mount" and route.name == "frontend"
    ]

    assert main._HAS_FRONTEND is bool(frontend_mounts)
    assert len(frontend_mounts) <= 1
