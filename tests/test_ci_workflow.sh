#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if grep -q 'tests/test_digest_api.py' .github/workflows/zhiji-check.yml; then
  echo "FAIL: CI references deleted tests/test_digest_api.py" >&2
  exit 1
fi

grep -Fq 'PYTHONPATH=src uv run --frozen python -m pytest -q' .github/workflows/zhiji-check.yml
grep -Fq 'npm run test:cinematic-scene' scripts/check.sh
grep -Fq 'npm run test:cinematic-ingest' scripts/check.sh
grep -Eq 'subosito/flutter-action@[0-9a-f]{40} # v2\.21\.0' .github/workflows/zhiji-check.yml
grep -Fq "flutter-version: '3.44.2'" .github/workflows/zhiji-check.yml
grep -Fq 'persist-credentials: false' .github/workflows/zhiji-check.yml
grep -Fq 'uv sync --frozen --group dev' .github/workflows/zhiji-check.yml
grep -Fq "BUNDLE_FROZEN: 'true'" .github/workflows/zhiji-check.yml
grep -Fq 'run: bundle check' .github/workflows/zhiji-check.yml
grep -Fq 'run: flutter analyze' .github/workflows/zhiji-check.yml
grep -Fq 'working-directory: desktop' .github/workflows/zhiji-check.yml
grep -Fq 'flutter build apk --debug' .github/workflows/zhiji-check.yml
grep -Fq 'android-gradle-sbom.cdx.json' .github/workflows/zhiji-check.yml
grep -Fq 'locked-dependencies-sbom.cdx.json' .github/workflows/zhiji-check.yml
grep -Fq 'Verify Android release signing guard' .github/workflows/zhiji-check.yml
grep -Fq 'run: brew install ffmpeg' .github/workflows/zhiji-check.yml

echo "ci workflow ok"
