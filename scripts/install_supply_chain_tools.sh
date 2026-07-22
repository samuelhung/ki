#!/usr/bin/env bash
set -euo pipefail

OSV_SCANNER_VERSION=2.4.0
SYFT_VERSION=1.49.0
INSTALL_DIR="${1:-.tools/bin}"
mkdir -p "$INSTALL_DIR"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"

case "$(uname -s)-$(uname -m)" in
  Darwin-x86_64)
    OSV_PLATFORM=darwin_amd64
    OSV_SHA256=088119325156321c34c456ac3703d6013538fd71cbac82b891ab34db491e4d66
    SYFT_PLATFORM=darwin_amd64
    SYFT_SHA256=a18ba5c48a4e75d0d87cae7b36b93bdfc04ddd5ea69b87bec9f7cd9431a8cdb9
    ;;
  Darwin-arm64)
    OSV_PLATFORM=darwin_arm64
    OSV_SHA256=9ca3185ad63e9ab54f7cb90f46a7362be02d80e37f0123d095a54355ea202f5d
    SYFT_PLATFORM=darwin_arm64
    SYFT_SHA256=4d137302fb3e049cb1b124b1cbd840a77280dc9f50a45a5a4389250a2228b3cb
    ;;
  Linux-x86_64)
    OSV_PLATFORM=linux_amd64
    OSV_SHA256=15314940c10d26af9c6649f150b8a47c1262e8fc7e17b1d1029b0e479e8ed8a0
    SYFT_PLATFORM=linux_amd64
    SYFT_SHA256=7aa2f03ee92739cf643279ba3990548b9925d4e22cae13f46831ee62821147fe
    ;;
  Linux-aarch64|Linux-arm64)
    OSV_PLATFORM=linux_arm64
    OSV_SHA256=44e580752910f0ff36ec99aff59af20f65df1e859aa31e5605a8f0d055b496e9
    SYFT_PLATFORM=linux_arm64
    SYFT_SHA256=c7c32de183c32368de197edba75e8dba7632915f7761bacd55149a9ca7fe0fa4
    ;;
  *)
    echo "unsupported supply-chain tool platform: $(uname -s)-$(uname -m)" >&2
    exit 1
    ;;
esac

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

OSV_FILE="$TEMP_DIR/osv-scanner"
curl -fsSL -o "$OSV_FILE" \
  "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_${OSV_PLATFORM}"
printf '%s  %s\n' "$OSV_SHA256" "$OSV_FILE" | shasum -a 256 -c -
install -m 0755 "$OSV_FILE" "$INSTALL_DIR/osv-scanner"

SYFT_ARCHIVE="$TEMP_DIR/syft.tar.gz"
curl -fsSL -o "$SYFT_ARCHIVE" \
  "https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}/syft_${SYFT_VERSION}_${SYFT_PLATFORM}.tar.gz"
printf '%s  %s\n' "$SYFT_SHA256" "$SYFT_ARCHIVE" | shasum -a 256 -c -
tar -xzf "$SYFT_ARCHIVE" -C "$TEMP_DIR" syft
install -m 0755 "$TEMP_DIR/syft" "$INSTALL_DIR/syft"

"$INSTALL_DIR/osv-scanner" --version
"$INSTALL_DIR/syft" version
