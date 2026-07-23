from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_lock_sbom import locked_components, osv_alias_components, write_lock_sbom


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_locked_components_reads_every_supported_non_android_lockfile(tmp_path: Path) -> None:
    _write(
        tmp_path / "uv.lock",
        'version = 1\n[[package]]\nname = "alpha"\nversion = "1.2.3"\n',
    )
    _write(
        tmp_path / "app/frontend/package-lock.json",
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {},
                    "node_modules/plain": {"version": "2.0.0"},
                    "node_modules/@scope/pkg": {"version": "3.0.0"},
                },
            }
        ),
    )
    _write(
        tmp_path / "desktop/pubspec.lock",
        """packages:
  dart_pkg:
    source: hosted
    version: "4.0.0"
  flutter:
    source: sdk
    version: "0.0.0"
""",
    )
    _write(
        tmp_path / "desktop/Gemfile.lock",
        """GEM
  specs:
    rack (3.1.0)
      base64
    base64 (0.3.0)
""",
    )
    _write(
        tmp_path / "desktop/macos/Podfile.lock",
        """PODS:
  - Sparkle (2.9.3)
  - LocalPlugin (0.0.1):
    - FlutterMacOS

DEPENDENCIES:
  - Sparkle
""",
    )
    _write(
        tmp_path / "desktop/android/app/gradle.lockfile",
        "com.example:widget:5.0.0=debugRuntimeClasspath\n",
    )

    assert locked_components(tmp_path) == {
        "pkg:pypi/alpha@1.2.3",
        "pkg:npm/plain@2.0.0",
        "pkg:npm/%40scope/pkg@3.0.0",
        "pkg:pub/dart_pkg@4.0.0",
        "pkg:gem/rack@3.1.0",
        "pkg:gem/base64@0.3.0",
        "pkg:cocoapods/Sparkle@2.9.3",
        "pkg:cocoapods/LocalPlugin@0.0.1",
    }


def test_write_lock_sbom_emits_exact_cyclonedx_components(tmp_path: Path) -> None:
    _write(tmp_path / "uv.lock", 'version = 1\n[[package]]\nname = "alpha"\nversion = "1.2.3"\n')
    _write(tmp_path / "app/frontend/package-lock.json", '{"lockfileVersion":3,"packages":{}}')
    _write(tmp_path / "desktop/pubspec.lock", "packages: {}\n")
    _write(tmp_path / "desktop/Gemfile.lock", "GEM\n  specs:\n")
    _write(tmp_path / "desktop/macos/Podfile.lock", "PODS:\n\nDEPENDENCIES:\n")
    output = tmp_path / "lock-sbom.cdx.json"

    assert write_lock_sbom(tmp_path, output) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.6"
    assert payload["components"] == [
        {"type": "library", "name": "alpha", "version": "1.2.3", "purl": "pkg:pypi/alpha@1.2.3"}
    ]


def test_cocoapods_require_osv_scannable_upstream_aliases(tmp_path: Path) -> None:
    _write(tmp_path / "desktop/macos/Podfile.lock", "PODS:\n  - Sparkle (2.9.3)\n\nDEPENDENCIES:\n")
    _write(
        tmp_path / ".github/security/cocoapods-security-coverage.yml",
        "pods:\n  Sparkle:\n    coverage: osv\n    purl: pkg:swift/github.com/sparkle-project/Sparkle@{version}\n",
    )

    assert osv_alias_components(tmp_path) == {"pkg:swift/github.com/sparkle-project/Sparkle@2.9.3"}

    _write(tmp_path / ".github/security/cocoapods-security-coverage.yml", "pods: {}\n")
    with pytest.raises(ValueError, match="missing CocoaPods security coverage: Sparkle"):
        osv_alias_components(tmp_path)

    _write(
        tmp_path / ".github/security/cocoapods-security-coverage.yml",
        "pods:\n  Sparkle:\n    coverage: osv\n    purl: pkg:generic/Sparkle@{version}\n",
    )
    with pytest.raises(ValueError, match="unsupported CocoaPods OSV aliases"):
        osv_alias_components(tmp_path)

    _write(
        tmp_path / ".github/security/cocoapods-security-coverage.yml",
        "pods:\n  Sparkle:\n    coverage: osv\n    purl: pkg:swift/github.com/sparkle-project/Sparkle@1.0.0\n",
    )
    with pytest.raises(ValueError, match="must contain exactly one.*version"):
        osv_alias_components(tmp_path)

    _write(
        tmp_path / ".github/security/cocoapods-security-coverage.yml",
        "pods:\n  Sparkle:\n    coverage: osv\n    purl: pkg:swift/github.com/sparkle-project/{version}@1.0.0\n",
    )
    with pytest.raises(ValueError, match="version field must be exactly"):
        osv_alias_components(tmp_path)


def test_local_pods_require_fresh_flutter_or_pub_coverage(tmp_path: Path) -> None:
    _write(
        tmp_path / "desktop/macos/Podfile.lock",
        "PODS:\n  - FlutterMacOS (1.0.0)\n  - tray_manager (0.0.1)\n\nDEPENDENCIES:\n",
    )
    _write(
        tmp_path / "desktop/pubspec.lock",
        """packages:
  tray_manager:
    source: hosted
    version: "0.2.4"
""",
    )
    _write(
        tmp_path / ".github/workflows/zhiji-check.yml",
        "steps:\n  - with:\n      flutter-version: '3.44.2'\n",
    )
    coverage = tmp_path / ".github/security/cocoapods-security-coverage.yml"
    _write(
        coverage,
        """pods:
  FlutterMacOS:
    coverage: flutter-sdk
    version: 3.44.2
  tray_manager:
    coverage: pub
    package: tray_manager
""",
    )

    assert osv_alias_components(tmp_path) == {"pkg:pub/tray_manager@0.2.4"}

    _write(
        coverage,
        """pods:
  FlutterMacOS:
    coverage: flutter-sdk
    version: 3.43.0
  tray_manager:
    coverage: pub
    package: tray_manager
""",
    )
    with pytest.raises(ValueError, match="Flutter SDK coverage version 3.43.0 does not match CI 3.44.2"):
        osv_alias_components(tmp_path)

    _write(
        coverage,
        """pods:
  FlutterMacOS:
    coverage: flutter-sdk
    version: 3.44.2
  tray_manager:
    coverage: pub
    package: unrelated
""",
    )
    with pytest.raises(ValueError, match="pub coverage must use the matching package"):
        osv_alias_components(tmp_path)
