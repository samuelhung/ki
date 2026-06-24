#!/bin/bash
# 生成 Sparkle appcast.xml 并用 EdDSA 签名
# 用法: ./generate_appcast.sh <version> <dmg_path>
set -euo pipefail

VERSION="$1"
DMG="$2"
RELEASE_DIR="$(dirname "$DMG")"
APPCAST="$RELEASE_DIR/appcast.xml"
SPARKLE_BIN="desktop/macos/Pods/Sparkle/bin"

if [ ! -f "$DMG" ]; then
    echo "❌ DMG 不存在: $DMG"
    exit 1
fi

echo "🔑 签名 DMG..."
SIGNATURE=$("$SPARKLE_BIN/sign_update" "$DMG" 2>/dev/null)
if [ -z "$SIGNATURE" ]; then
    echo "❌ 签名失败"
    exit 1
fi

DMG_SIZE=$(stat -f%z "$DMG")
DMG_NAME=$(basename "$DMG")
TITLE="知几桌面端 v${VERSION}"
PUBDATE=$(date -u +"%a, %d %b %Y %H:%M:%S %z")
DOWNLOAD_URL="https://github.com/samuelhung/ki/releases/download/v${VERSION}/${DMG_NAME}"

# 读取 CHANGELOG（如果有的话）
NOTES="知几桌面端 v${VERSION}"

echo "📋 生成 appcast.xml..."

cat > "$APPCAST" << EOF
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>知几</title>
    <description>知几 — 知识情报中心桌面端更新</description>
    <language>zh-CN</language>
    <item>
      <title>${TITLE}</title>
      <description><![CDATA[${NOTES}]]></description>
      <pubDate>${PUBDATE}</pubDate>
      <enclosure
        url="${DOWNLOAD_URL}"
        sparkle:version="${VERSION}"
        sparkle:shortVersionString="${VERSION}"
        sparkle:edSignature="${SIGNATURE}"
        length="${DMG_SIZE}"
        type="application/octet-stream"
      />
    </item>
  </channel>
</rss>
EOF

echo "✅ appcast.xml 已生成: $APPCAST"
echo "   DMG: $DMG_NAME ($(echo "scale=1; $DMG_SIZE/1024/1024" | bc)MB)"
echo "   签名: ${SIGNATURE:0:20}..."
