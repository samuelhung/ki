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
if grep -Fq 'flutter build apk' .github/workflows/zhiji-check.yml; then
  echo 'FAIL: CI still builds Android APKs' >&2
  exit 1
fi
if grep -Fq 'android-gradle-sbom.cdx.json' .github/workflows/zhiji-check.yml; then
  echo 'FAIL: CI still generates a Gradle SBOM' >&2
  exit 1
fi
grep -Fq 'locked-dependencies-sbom.cdx.json' .github/workflows/zhiji-check.yml
if grep -Fq 'Android release signing' .github/workflows/zhiji-check.yml; then
  echo 'FAIL: CI still checks Android release signing' >&2
  exit 1
fi
if grep -Fq -- '--runtime-lock-root' .github/workflows/zhiji-check.yml; then
  echo 'FAIL: CI still uses an Android runtime lock root' >&2
  exit 1
fi
grep -Fq 'run: brew install ffmpeg' .github/workflows/zhiji-check.yml

echo "ci workflow ok"
