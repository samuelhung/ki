from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def test_active_product_versions_are_synchronized_to_2_0_0() -> None:
    expected = {
        "pyproject.toml": 'version = "2.0.0"',
        "src/zhiji_backend/__init__.py": '__version__ = "2.0.0"',
        "app/frontend/src/constants.ts": 'APP_VERSION = "2.0.0"',
        "app/frontend/vite.config.ts": "appVersion = '2.0.0'",
        "app/frontend/public/about.html": "v2.0.0",
        "desktop/lib/main.dart": "_desktopVersion = '2.0.0'",
        "desktop/pubspec.yaml": "version: 2.0.0+90",
    }

    for relative_path, marker in expected.items():
        assert marker in _read(relative_path), relative_path


def test_system_status_distinguishes_sqlite_api_and_web_versions() -> None:
    source = _read("app/frontend/src/pages/CinematicSystemCenter.tsx")
    styles = _read("app/frontend/src/components/cinematic-system/cinematic-system.css")

    assert "SQLite {databaseState}" in source
    assert "API {health.data?.version || APP_VERSION}" in source
    assert "Web {APP_VERSION}" in source
    assert "主库 {databaseState}" not in source
    assert 'className="system-shell-status__health"' in source
    assert 'className="system-shell-status__versions"' in source
    assert ".system-shell-status__health" in styles
    assert ".system-shell-status__versions" in styles
