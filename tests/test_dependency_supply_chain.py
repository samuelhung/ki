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


def test_mobile_dependency_and_signing_inputs_are_locked() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")
    wrapper = (ROOT / "desktop" / "android" / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(
        encoding="utf-8"
    )
    android_build = (ROOT / "desktop" / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    android_settings = (ROOT / "desktop" / "android" / "settings.gradle.kts").read_text(encoding="utf-8")
    root_android_build = (ROOT / "desktop" / "android" / "build.gradle.kts").read_text(encoding="utf-8")
    gradle_locks = sorted((ROOT / "desktop" / "android").glob("**/gradle.lockfile"))

    assert "flutter pub get --enforce-lockfile" in workflow
    assert 'id("com.android.application") version "9.1.1" apply false' in android_settings
    assert "load Gem.bin_path(\"cocoapods\", \"pod\")" in workflow
    assert "COCOAPODS_VERSION: '1.16.2'" in workflow
    assert "BUNDLE_FROZEN: 'true'" in workflow
    assert "ruby-version: '3.1.6'" in workflow
    assert "bundle check" in workflow
    assert "RUBYOPT: -rlogger" not in workflow
    assert "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.3.1-all.zip" in wrapper
    assert "distributionSha256Sum=17f277867f6914d61b1aa02efab1ba7bb439ad652ca485cd8ca6842fccec6e43" in wrapper
    assert "lockAllConfigurations()" in root_android_build
    assert "LockMode.STRICT" in root_android_build
    assert "projectDir.toPath().startsWith(repositoryRoot)" in root_android_build
    assert gradle_locks
    assert all(lock.read_text(encoding="utf-8").strip() for lock in gradle_locks)
    assert "ANDROID_KEYSTORE_PATH" in android_build
    assert "Production Android release signing is required" in android_build
    assert "gradle.taskGraph.whenReady" in android_build
    assert 'signingConfigs.getByName("debug")' not in android_build
    assert "Verify Android release signing guard" in workflow
    assert ":app:assembleRelease --dry-run" in workflow
    assert "Production Android release signing is required" in workflow


def test_android_release_task_graph_uses_kotlin_action_overload() -> None:
    android_build = (ROOT / "desktop" / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")

    assert "object : Action<TaskExecutionGraph>" in android_build
    assert "override fun execute(taskGraph: TaskExecutionGraph)" in android_build


def test_android_build_tool_security_overrides_are_scoped_and_locked() -> None:
    android_build = (ROOT / "desktop" / "android" / "build.gradle.kts").read_text(encoding="utf-8")
    gradle_lock = (ROOT / "desktop" / "android" / "app" / "gradle.lockfile").read_text(encoding="utf-8")

    assert 'name.startsWith("_internal-unified-test-platform")' in android_build
    assert 'requested.group == "io.netty"' in android_build
    assert 'requested.version in setOf("4.1.93.Final", "4.1.110.Final")' in android_build
    assert 'useVersion("4.1.135.Final")' in android_build
    assert 'requested.group == "com.google.protobuf"' in android_build
    assert 'requested.version?.startsWith("3.") == true' in android_build
    assert 'useVersion("3.25.5")' in android_build
    assert 'requested.group == "org.bouncycastle"' in android_build
    assert 'requested.version == "1.79"' in android_build
    assert 'useVersion("1.80.2")' in android_build
    assert "io.netty:netty-handler:4.1.135.Final=" in gradle_lock
    assert "com.google.protobuf:protobuf-java:4.28.3=" in gradle_lock
    assert "com.google.protobuf:protobuf-kotlin:4.28.3=" in gradle_lock
    assert "org.bouncycastle:bcprov-jdk18on:1.80.2=" in gradle_lock
    assert "io.netty:netty-handler:4.1.110.Final=" not in gradle_lock
    assert "io.netty:netty-handler:4.1.93.Final=" not in gradle_lock
    assert "com.google.protobuf:protobuf-java:3.24.4=" not in gradle_lock
    assert "com.google.protobuf:protobuf-kotlin:3.24.4=" not in gradle_lock
    assert "org.bouncycastle:bcprov-jdk18on:1.79=" not in gradle_lock


def test_android_lint_bundle_vulnerability_exceptions_are_exact_and_temporary() -> None:
    payload = yaml.safe_load(
        (ROOT / ".github" / "security" / "vulnerability-exceptions.yml").read_text(encoding="utf-8")
    )
    entries = {
        (entry["id"], entry["ecosystem"], entry["package"], str(entry["version"])): entry
        for entry in payload["exceptions"]
    }
    expected = {
        ("GHSA-735f-pc8j-v9w8", "Maven", "com.google.protobuf:protobuf-java", "2.6.1"),
        ("GHSA-wrvw-hg22-4m67", "Maven", "com.google.protobuf:protobuf-java", "2.6.1"),
        ("GHSA-2r2c-cx56-8933", "Maven", "org.jline:jline-remote-telnet", "3.24.1"),
        ("GHSA-47qp-hqvx-6r3f", "Maven", "org.jline:jline-remote-telnet", "3.24.1"),
    }

    assert expected <= entries.keys()
    for key in expected:
        entry = entries[key]
        assert entry["expires"].isoformat() == "2026-09-30"
        assert "Android Lint" in entry["reason"]
        assert "APK" in entry["impact"]


def test_ci_executes_locked_android_graph_and_generates_gradle_sbom() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")

    assert "GRADLE_USER_HOME: ${{ runner.temp }}/gradle-home" not in workflow
    assert 'echo "GRADLE_USER_HOME=$RUNNER_TEMP/gradle-home" >> "$GITHUB_ENV"' in workflow
    assert "flutter build apk --debug" in workflow
    assert "--write-locks" not in workflow
    assert 'scan dir:"$GRADLE_USER_HOME/caches/modules-2/files-2.1"' in workflow
    assert "android-gradle-sbom.cdx.json" in workflow
    assert "generate_lock_sbom.py" in workflow
    assert "locked-dependencies-sbom.cdx.json" in workflow
    assert "--require-lock-root ." in workflow
    assert '--sbom "$RUNNER_TEMP/source-sbom.cdx.json"' in workflow
    assert '--sbom "$RUNNER_TEMP/android-gradle-sbom.cdx.json"' in workflow
    assert '--sbom "$RUNNER_TEMP/locked-dependencies-sbom.cdx.json"' in workflow


def test_supply_chain_tools_and_dependabot_are_configured() -> None:
    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(encoding="utf-8")
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "install_supply_chain_tools.sh").read_text(encoding="utf-8")

    action_refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)
    assert action_refs and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    assert "permissions:\n  contents: read" in workflow
    assert "runs-on: macos-14" in workflow
    assert "persist-credentials: false" in workflow
    for ecosystem in ("github-actions", "npm", "uv", "pub", "gradle", "bundler"):
        assert f'package-ecosystem: "{ecosystem}"' in dependabot
    assert "OSV_SCANNER_VERSION=2.4.0" in installer
    assert "SYFT_VERSION=1.49.0" in installer
    assert "shasum -a 256 -c" in installer
    assert 'gradle-distribution.zip" | shasum -a 256 -c -' in workflow
    assert "cyclonedx-json" in workflow
    assert '--sbom "$RUNNER_TEMP/source-sbom.cdx.json"' in workflow
    assert "vulnerability-exceptions.yml" in workflow
