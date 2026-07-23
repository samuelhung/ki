#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_JSON = ROOT / "app/frontend/package.json"


def expected_versions(package_json: Path = PACKAGE_JSON) -> tuple[str, str]:
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    return payload["engines"]["node"], payload["packageManager"].rsplit("@", 1)[1]


def validate_versions(expected_node: str, expected_npm: str, actual_node: str, actual_npm: str) -> None:
    if actual_node.removeprefix("v") != expected_node:
        raise ValueError(f"expected Node {expected_node}, found {actual_node.removeprefix('v')}")
    if actual_npm != expected_npm:
        raise ValueError(f"expected npm {expected_npm}, found {actual_npm}")


def command_version(command: str, *args: str) -> str:
    return subprocess.check_output([command, *args], text=True).strip()


def main() -> int:
    expected_node, expected_npm = expected_versions()
    try:
        validate_versions(
            expected_node,
            expected_npm,
            command_version("node", "--version"),
            command_version("npm", "--version"),
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    print(f"frontend toolchain ok: Node {expected_node}, npm {expected_npm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
