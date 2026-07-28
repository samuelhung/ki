from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_python_dependencies_are_frozen_with_uv() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = pyproject["dependency-groups"]["dev"]

    assert (ROOT / "uv.lock").is_file()
    assert any(re.match(r"pytest(?:[<=>!~].*)?$", item) for item in dev_dependencies)
    assert any(re.match(r"httpx(?:[<=>!~].*)?$", item) for item in dev_dependencies)
    assert any(re.match(r"build(?:[<=>!~].*)?$", item) for item in dev_dependencies)
    assert any(re.match(r"setuptools(?:[<=>!~].*)?$", item) for item in dev_dependencies)
    assert any(re.match(r"wheel(?:[<=>!~].*)?$", item) for item in dev_dependencies)


def test_local_check_uses_the_frozen_uv_environment() -> None:
    check_script = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")

    assert re.search(r'"\$UV_BIN" lock --check', check_script)
    assert re.search(r'"\$UV_BIN" sync --frozen', check_script)
    assert re.search(r"PYTHON_BIN=\([^\n]*run --frozen python\)", check_script)
    assert '"${PYTHON_BIN[@]}" scripts/check_frontend_toolchain.py' in check_script


def test_ci_and_wheel_build_use_frozen_uv_dependencies() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")
    wheel_builder = (ROOT / "scripts" / "build_backend_wheel.py").read_text(encoding="utf-8")

    assert "uv sync --frozen" in workflow
    assert "uv lock --check" in workflow
    assert "uv run --frozen" in workflow
    tree = ast.parse(wheel_builder)
    commands = [
        [item.value for item in node.elts if isinstance(item, ast.Constant)]
        for node in ast.walk(tree)
        if isinstance(node, ast.List)
    ]
    assert any(command[:6] == ["uv", "run", "--frozen", "python", "-m", "build"] for command in commands)
    assert any(command[:3] == ["uv", "lock", "--check"] for command in commands)
    assert any(command[:3] == ["uv", "sync", "--frozen"] for command in commands)
    assert any(command == ["npm", "ci"] for command in commands)


def test_frontend_direct_dependencies_are_exact_and_integrity_locked() -> None:
    package = json.loads((ROOT / "app" / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "app" / "frontend" / "package-lock.json").read_text(encoding="utf-8"))

    assert package["packageManager"] == "npm@10.9.2"
    assert package["engines"]["node"] == "22.17.0"
    for group in ("dependencies", "devDependencies"):
        for name, declared in package[group].items():
            assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", declared), (name, declared)
            locked = lock["packages"][f"node_modules/{name}"]
            assert locked["version"] == declared
            assert locked["resolved"].startswith("https://registry.npmjs.org/")
            assert locked["integrity"].startswith("sha512-")


def test_frontend_typescript_tests_enable_the_locked_node22_loader() -> None:
    package = json.loads((ROOT / "app" / "frontend" / "package.json").read_text(encoding="utf-8"))
    for script_name in (
        "test:cinematic-scene",
        "test:cinematic-ingest",
        "test:media-transport",
    ):
        assert package["scripts"][script_name].startswith("node --experimental-strip-types --test ")

    assert "tsx" not in package.get("devDependencies", {})


def test_desktop_dependency_inputs_are_locked_without_android_target() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")
    metadata = (ROOT / "desktop" / ".metadata").read_text(encoding="utf-8")
    gitignore = (ROOT / "desktop" / ".gitignore").read_text(encoding="utf-8")
    pubspec = yaml.safe_load((ROOT / "desktop" / "pubspec.yaml").read_text(encoding="utf-8"))
    pubspec_lock = yaml.safe_load((ROOT / "desktop" / "pubspec.lock").read_text(encoding="utf-8"))
    pod_security_coverage = yaml.safe_load(
        (ROOT / ".github" / "security" / "cocoapods-security-coverage.yml").read_text(encoding="utf-8")
    )
    gemfile = (ROOT / "desktop" / "Gemfile").read_text(encoding="utf-8")
    gemfile_lock = (ROOT / "desktop" / "Gemfile.lock").read_text(encoding="utf-8")
    podfile_lock = (ROOT / "desktop" / "macos" / "Podfile.lock").read_text(encoding="utf-8")

    assert not (ROOT / "desktop" / "android").exists()
    assert "platform: android" not in metadata
    assert "/android/" not in gitignore
    assert "flutter pub get --enforce-lockfile" in workflow
    assert "load Gem.bin_path(\"cocoapods\", \"pod\")" in workflow
    assert "COCOAPODS_VERSION: '1.17.0'" in workflow
    assert "BUNDLE_FROZEN: 'true'" in workflow
    assert "ruby-version: '3.1.6'" in workflow
    assert "bundle check" in workflow
    assert "RUBYOPT: -rlogger" not in workflow
    assert pubspec["dependencies"]["tray_manager"] == "^0.5.3"
    assert pubspec["dependencies"]["window_manager"] == "^0.5.2"
    assert pubspec_lock["packages"]["tray_manager"]["version"] == "0.5.3"
    assert pubspec_lock["packages"]["window_manager"]["version"] == "0.5.2"
    assert 'gem "cocoapods", "1.17.0"' in gemfile
    assert "cocoapods (= 1.17.0)" in gemfile_lock
    assert "COCOAPODS: 1.17.0" in podfile_lock
    assert "tray_manager" not in podfile_lock
    assert "window_manager" not in podfile_lock
    assert set(pod_security_coverage["pods"]) == {"FlutterMacOS", "Sparkle"}


def test_android_vulnerability_exceptions_are_absent() -> None:
    payload = yaml.safe_load(
        (ROOT / ".github" / "security" / "vulnerability-exceptions.yml").read_text(encoding="utf-8")
    )
    entries = payload["exceptions"]

    assert all(entry["ecosystem"].casefold() != "maven" for entry in entries)
    assert all("android" not in f'{entry["reason"]} {entry["impact"]}'.casefold() for entry in entries)


def test_ci_generates_non_android_supply_chain_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")

    assert "GRADLE_USER_HOME" not in workflow
    assert "flutter build apk" not in workflow
    assert "Android release" not in workflow
    assert "ANDROID_KEYSTORE" not in workflow
    assert "--write-locks" not in workflow
    assert "gradle-distribution.zip" not in workflow
    assert "android-gradle-sbom.cdx.json" not in workflow
    assert "generate_lock_sbom.py" in workflow
    assert "locked-dependencies-sbom.cdx.json" in workflow
    assert "--require-lock-root ." in workflow
    assert '--sbom "$RUNNER_TEMP/source-sbom.cdx.json"' in workflow
    assert '--sbom "$RUNNER_TEMP/locked-dependencies-sbom.cdx.json"' in workflow
    assert "--runtime-lock-root" not in workflow


def test_supply_chain_tools_and_dependabot_are_configured() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "install_supply_chain_tools.sh").read_text(encoding="utf-8")

    action_refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)
    assert action_refs and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    assert "permissions:\n  contents: read" in workflow
    assert "runs-on: macos-14" in workflow
    assert "persist-credentials: false" in workflow
    for ecosystem in ("github-actions", "npm", "uv", "pub", "bundler"):
        assert f'package-ecosystem: "{ecosystem}"' in dependabot
    assert 'package-ecosystem: "gradle"' not in dependabot
    assert "OSV_SCANNER_VERSION=2.4.0" in installer
    assert "SYFT_VERSION=1.49.0" in installer
    assert "shasum -a 256 -c" in installer
    assert "cyclonedx-json" in workflow
    assert '--sbom "$RUNNER_TEMP/source-sbom.cdx.json"' in workflow
    assert "vulnerability-exceptions.yml" in workflow


def test_dependabot_groups_react_runtime_updates() -> None:
    dependabot = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    npm_update = next(
        update
        for update in dependabot["updates"]
        if update["package-ecosystem"] == "npm" and update["directory"] == "/app/frontend"
    )

    assert npm_update["groups"]["react-runtime"]["patterns"] == ["react", "react-dom"]


def test_cocoapods_updates_are_checked_weekly_with_locked_tools() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "cocoapods-outdated.yml"
    assert workflow_path.is_file()
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "cron:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "runs-on: macos-14" in workflow
    assert "persist-credentials: false" in workflow
    assert "flutter pub get --enforce-lockfile" in workflow
    assert "bundle check" in workflow
    assert "outdated --repo-update --no-ansi" in workflow
    assert "The following pod updates are available:" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1" in workflow
    action_refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)
    assert action_refs and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
