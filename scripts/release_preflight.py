#!/usr/bin/env python3
"""Fail-closed release preflight for source metadata and built artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from scripts.release_contract import (
        ReleaseContract,
        ReleaseContractError,
        load_release_contract,
        validate_candidate_appcast,
        validate_release_artifacts,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from release_contract import (  # type: ignore[no-redef]
        ReleaseContract,
        ReleaseContractError,
        load_release_contract,
        validate_candidate_appcast,
        validate_release_artifacts,
    )


def run_preflight(
    root: Path,
    tag: str,
    artifacts_dir: Path,
    candidate_appcast: Path,
) -> ReleaseContract:
    contract = load_release_contract(root.resolve(), tag)
    validate_candidate_appcast(candidate_appcast.resolve(), contract)
    validate_release_artifacts(artifacts_dir.resolve(), contract)
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a complete Zhiji release candidate")
    parser.add_argument("tag", help="canonical release tag, for example v2.0.0+90")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--candidate-appcast", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        contract = run_preflight(args.root, args.tag, args.artifacts_dir, args.candidate_appcast)
    except (OSError, ValueError, ReleaseContractError) as exc:
        print(f"release preflight failed: {exc}", file=sys.stderr)
        return 2
    print(f"release preflight ok: {contract.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
