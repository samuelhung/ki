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
grep -Fq 'subosito/flutter-action@v2' .github/workflows/zhiji-check.yml
grep -Fq "flutter-version: '3.44.2'" .github/workflows/zhiji-check.yml
grep -Fq 'run: flutter analyze' .github/workflows/zhiji-check.yml
grep -Fq 'working-directory: desktop' .github/workflows/zhiji-check.yml
grep -Fq 'run: brew install ffmpeg' .github/workflows/zhiji-check.yml

echo "ci workflow ok"
