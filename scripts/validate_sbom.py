#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.generate_lock_sbom import locked_components
except ModuleNotFoundError:  # Direct execution: python scripts/validate_sbom.py
    from generate_lock_sbom import locked_components


REQUIRED_ECOSYSTEMS = {"pypi", "npm", "pub", "gem", "cocoapods", "maven"}


def validate_sbom(*paths: Path, required_purls: set[str] | None = None) -> int:
    ecosystems: set[str] = set()
    purls: set[str] = set()
    component_count = 0
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("bomFormat") != "CycloneDX" or not payload.get("specVersion"):
            raise ValueError(f"expected CycloneDX metadata in {path}")
        components = payload.get("components")
        if not isinstance(components, list) or not components:
            raise ValueError(f"no components in {path}")
        component_count += len(components)
        document_purls = {
            purl
            for component in components
            if isinstance(component, dict)
            and isinstance((purl := component.get("purl")), str)
            and purl.startswith("pkg:")
        }
        purls.update(document_purls)
        ecosystems.update(purl.split(":", 1)[1].split("/", 1)[0] for purl in document_purls)
    missing = REQUIRED_ECOSYSTEMS - ecosystems
    if missing:
        raise ValueError(f"missing ecosystems: {', '.join(sorted(missing))}")
    missing_purls = (required_purls or set()) - purls
    if missing_purls:
        sample = ", ".join(sorted(missing_purls)[:10])
        raise ValueError(f"missing locked components ({len(missing_purls)}): {sample}")
    return component_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--require-lock-root", type=Path)
    args = parser.parse_args()
    try:
        required = locked_components(args.require_lock_root.resolve()) if args.require_lock_root else None
        component_count = validate_sbom(*args.paths, required_purls=required)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"invalid SBOM: {exc}")
        return 1
    print(f"CycloneDX SBOM ok: {component_count} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
