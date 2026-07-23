from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETIRED_ENTRYPOINTS = (
    "scripts/release.sh",
    "scripts/release-check.py",
    "scripts/generate_appcast.sh",
    "scripts/install.sh",
    "desktop/scripts/build_release.py",
)


def test_conflicting_release_and_install_entrypoints_are_hard_disabled() -> None:
    for relative in RETIRED_ENTRYPOINTS:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "ZHIJI_RETIRED_ENTRYPOINT" in source, relative
        assert "scripts/build_release.py" in source, relative
        assert "scripts/publish_release.py" in source, relative
        assert "scripts/deploy_backend.py" in source, relative
    assert not (ROOT / "desktop" / "deploy" / "com.zhiji.backend.plist").exists()


def test_unified_check_uses_release_preflight_instead_of_legacy_diagnostics() -> None:
    source = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")

    assert "scripts/release_preflight.py" in source
    assert "scripts/release-check.py" not in source


def test_readme_documents_only_the_verified_release_and_atomic_deploy_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    for required in (
        "scripts/build_release.py v2.0.0+90",
        "scripts/release_preflight.py v2.0.0+90",
        "scripts/publish_release.py v2.0.0+90",
        "scripts/deploy_backend.py v2.0.0+90",
    ):
        assert required in readme
    for retired in (
        "scripts/release-check.py",
        "pip install --force-reinstall",
        "./scripts/release.sh",
    ):
        assert retired not in readme
        assert retired not in architecture
