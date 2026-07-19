#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if grep -q 'tests/test_digest_api.py' .github/workflows/zhiji-check.yml; then
  echo "FAIL: CI references deleted tests/test_digest_api.py" >&2
  exit 1
fi

grep -Fq 'PYTHONPATH=src python -m pytest -q' .github/workflows/zhiji-check.yml
grep -Fq 'npm run test:cinematic-scene' scripts/check.sh
grep -Fq 'npm run test:cinematic-ingest' scripts/check.sh

echo "ci workflow ok"
