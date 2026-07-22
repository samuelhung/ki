#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from urllib.parse import quote, unquote

import yaml


def _purl(ecosystem: str, name: str, version: str) -> str:
    return f"pkg:{ecosystem}/{quote(name, safe='/._~-')}@{quote(version, safe='._~-')}"


def _uv_purls(path: Path) -> set[str]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return {_purl("pypi", item["name"], item["version"]) for item in payload.get("package", [])}


def _npm_purls(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for package_path, item in payload.get("packages", {}).items():
        if not package_path or not isinstance(item, dict) or not isinstance(item.get("version"), str):
            continue
        name = package_path.rsplit("node_modules/", 1)[-1]
        result.add(_purl("npm", name, item["version"]))
    return result


def _pub_versions(path: Path) -> dict[str, str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result: dict[str, str] = {}
    for name, item in (payload.get("packages") or {}).items():
        if isinstance(item, dict) and item.get("source") == "hosted" and isinstance(item.get("version"), str):
            result[name] = item["version"]
    return result


def _pub_purls(path: Path) -> set[str]:
    return {_purl("pub", name, version) for name, version in _pub_versions(path).items()}


def _gem_purls(path: Path) -> set[str]:
    result: set[str] = set()
    in_specs = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "  specs:":
            in_specs = True
            continue
        if in_specs and line and not line.startswith(" "):
            break
        if not in_specs:
            continue
        match = re.fullmatch(r"    ([A-Za-z0-9_.-]+) \(([^ )]+)\)", line)
        if match:
            result.add(_purl("gem", match.group(1), match.group(2)))
    return result


def _pod_versions(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    in_pods = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "PODS:":
            in_pods = True
            continue
        if in_pods and line and not line.startswith(" "):
            break
        if not in_pods:
            continue
        match = re.fullmatch(r"  - ([^ ]+) \(([^ )]+)\):?", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def _pod_purls(path: Path) -> set[str]:
    return {_purl("cocoapods", name, version) for name, version in _pod_versions(path).items()}


def _gradle_purls(path: Path) -> set[str]:
    result: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("empty="):
            continue
        coordinate = line.rsplit("=", 1)[0]
        group, artifact, version = coordinate.split(":", 2)
        result.add(_purl("maven", f"{group}/{artifact}", version))
    return result


def locked_components(root: Path) -> set[str]:
    return set().union(
        _uv_purls(root / "uv.lock"),
        _npm_purls(root / "app/frontend/package-lock.json"),
        _pub_purls(root / "desktop/pubspec.lock"),
        _gem_purls(root / "desktop/Gemfile.lock"),
        _pod_purls(root / "desktop/macos/Podfile.lock"),
        _gradle_purls(root / "desktop/android/app/gradle.lockfile"),
    )


def osv_alias_components(root: Path) -> set[str]:
    pod_versions = _pod_versions(root / "desktop/macos/Podfile.lock")
    if not pod_versions:
        return set()

    mapping_path = root / ".github/security/cocoapods-security-coverage.yml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    coverage = payload.get("pods") or {}
    if not isinstance(coverage, dict) or not all(isinstance(key, str) and isinstance(value, dict) for key, value in coverage.items()):
        raise ValueError(f"invalid CocoaPods security coverage in {mapping_path}")

    missing = set(pod_versions) - set(coverage)
    stale = set(coverage) - set(pod_versions)
    if missing:
        raise ValueError(f"missing CocoaPods security coverage: {', '.join(sorted(missing))}")
    if stale:
        raise ValueError(f"stale CocoaPods security coverage: {', '.join(sorted(stale))}")

    modes = {entry.get("coverage") for entry in coverage.values()}
    pub_versions = _pub_versions(root / "desktop/pubspec.lock") if "pub" in modes else {}
    ci_flutter_version = ""
    if "flutter-sdk" in modes:
        workflow = (root / ".github/workflows/zhiji-check.yml").read_text(encoding="utf-8")
        flutter_versions = set(re.findall(r"flutter-version:\s*['\"]([^'\"]+)['\"]", workflow))
        if len(flutter_versions) != 1:
            raise ValueError("CI must declare exactly one Flutter version")
        ci_flutter_version = next(iter(flutter_versions))

    result: set[str] = set()
    for name, pod_version in pod_versions.items():
        entry = coverage[name]
        mode = entry.get("coverage")
        if mode == "osv" and set(entry) == {"coverage", "purl"} and isinstance(entry.get("purl"), str):
            template = entry["purl"]
            if template.count("{version}") != 1:
                raise ValueError(f"CocoaPods OSV alias for {name} must contain exactly one {{version}} placeholder")
            if template.rsplit("@", 1)[-1] != "{version}":
                raise ValueError(f"CocoaPods OSV alias version field must be exactly {{version}} for {name}")
            purl = template.replace("{version}", pod_version)
            if not purl.startswith(("pkg:pub/", "pkg:swift/")):
                raise ValueError(f"unsupported CocoaPods OSV aliases: {purl}")
            result.add(purl)
        elif mode == "pub" and set(entry) == {"coverage", "package"} and isinstance(entry.get("package"), str):
            package = entry["package"]
            if package != name:
                raise ValueError(f"CocoaPods pub coverage must use the matching package for {name}")
            if package not in pub_versions:
                raise ValueError(f"CocoaPods pub coverage package is not locked: {package}")
            result.add(_purl("pub", package, pub_versions[package]))
        elif mode == "flutter-sdk" and set(entry) == {"coverage", "version"}:
            if name != "FlutterMacOS":
                raise ValueError(f"flutter-sdk coverage is only valid for FlutterMacOS, not {name}")
            version = str(entry["version"])
            if version != ci_flutter_version:
                raise ValueError(f"Flutter SDK coverage version {version} does not match CI {ci_flutter_version}")
        else:
            raise ValueError(f"invalid CocoaPods security coverage for {name}")
    return result


def _component_from_purl(purl: str) -> dict[str, str]:
    package, version = purl.rsplit("@", 1)
    name = unquote(package.split("/", 1)[1])
    return {
        "type": "library",
        "name": name,
        "version": unquote(version),
        "purl": purl,
    }


def write_lock_sbom(root: Path, output: Path) -> int:
    purls = sorted(locked_components(root) | osv_alias_components(root))
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [_component_from_purl(purl) for purl in purls],
    }
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return len(purls)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    count = write_lock_sbom(args.root.resolve(), args.output.resolve())
    print(f"CycloneDX lock SBOM written: {count} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
