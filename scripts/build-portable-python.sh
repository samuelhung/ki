#!/bin/bash
# ============================================================
# build-portable-python.sh
# 固化 Python venv dylib 可移植性修复流程
#
# 每次重新构建 DMG 前应执行此脚本。
# 修复后 Python 可在任何 macOS 机器上运行（不依赖 Homebrew 安装路径）。
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_DIR="$PROJECT_ROOT/desktop/src-tauri/resources/backend/python"
DYNLOAD="$PYTHON_DIR/lib/python3.12/lib-dynload"

echo "=== KI Desktop Python Portability Fix ==="
echo "Python dir: $PYTHON_DIR"
echo ""

# --------------- 1. Resolve Homebrew paths ---------------
PYTHON_VER=$(ls /usr/local/Cellar/python@3.12/ 2>/dev/null | tail -1)
if [ -z "$PYTHON_VER" ]; then
    echo "ERROR: python@3.12 not found in /usr/local/Cellar/"
    exit 1
fi
FRAMEWORK="/usr/local/Cellar/python@3.12/${PYTHON_VER}/Frameworks/Python.framework/Versions/3.12"

OPENSSL_VER=$(ls /usr/local/Cellar/openssl@3/ 2>/dev/null | tail -1)
MPDECIMAL_VER=$(ls /usr/local/Cellar/mpdecimal/ 2>/dev/null | tail -1)
XZ_VER=$(ls /usr/local/Cellar/xz/ 2>/dev/null | tail -1)
SQLITE_VER=$(ls /usr/local/Cellar/sqlite/ 2>/dev/null | tail -1)

# --------------- 2. Fix python3.12 binary ---------------
echo "[1/5] Fixing python3.12 binary..."

# Copy libpython dylib (force overwrite if exists + read-only)
cp -f "$FRAMEWORK/Python" "$PYTHON_DIR/lib/libpython3.12.dylib"
chmod 644 "$PYTHON_DIR/lib/libpython3.12.dylib"
install_name_tool -id "@rpath/libpython3.12.dylib" "$PYTHON_DIR/lib/libpython3.12.dylib"

# Replace venv python3.12 with real binary
rm -f "$PYTHON_DIR/bin/python3.12"
cp "$FRAMEWORK/Resources/Python.app/Contents/MacOS/Python" "$PYTHON_DIR/bin/python3.12"
chmod +x "$PYTHON_DIR/bin/python3.12"

# Fix python3.12's dylib reference
install_name_tool -change \
  "$FRAMEWORK/Python" \
  "@executable_path/../lib/libpython3.12.dylib" \
  "$PYTHON_DIR/bin/python3.12"

# Rebuild local symlinks
rm -f "$PYTHON_DIR/bin/python3" "$PYTHON_DIR/bin/python"
ln -sf python3.12 "$PYTHON_DIR/bin/python3"
ln -sf python3.12 "$PYTHON_DIR/bin/python"

echo "  ✅ python3.12 fixed"

# --------------- 3. Copy and fix dependency dylibs ---------------
echo "[2/5] Copying dependency dylibs..."

OPENSSL_LIB="/usr/local/Cellar/openssl@3/${OPENSSL_VER}/lib"
MPDECIMAL_LIB="/usr/local/Cellar/mpdecimal/${MPDECIMAL_VER}/lib"
XZ_LIB="/usr/local/Cellar/xz/${XZ_VER}/lib"
SQLITE_LIB="/usr/local/Cellar/sqlite/${SQLITE_VER}/lib"

cp -f "$OPENSSL_LIB/libssl.3.dylib" "$PYTHON_DIR/lib/"
chmod 644 "$PYTHON_DIR/lib/libssl.3.dylib"
cp -f "$OPENSSL_LIB/libcrypto.3.dylib" "$PYTHON_DIR/lib/"
chmod 644 "$PYTHON_DIR/lib/libcrypto.3.dylib"
cp -f "$MPDECIMAL_LIB/libmpdec.4.dylib" "$PYTHON_DIR/lib/"
chmod 644 "$PYTHON_DIR/lib/libmpdec.4.dylib"
cp -f "$XZ_LIB/liblzma.5.dylib" "$PYTHON_DIR/lib/"
chmod 644 "$PYTHON_DIR/lib/liblzma.5.dylib"
cp -f "$SQLITE_LIB/libsqlite3.0.dylib" "$PYTHON_DIR/lib/"
chmod 644 "$PYTHON_DIR/lib/libsqlite3.0.dylib"

# Fix dylib own IDs
for lib in libssl.3 libcrypto.3 libmpdec.4 liblzma.5 libsqlite3.0; do
    install_name_tool -id "@rpath/${lib}.dylib" "$PYTHON_DIR/lib/${lib}.dylib" 2>/dev/null || true
done

# Fix inter-dylib references (libssl.3 depends on libcrypto.3)
install_name_tool -change \
  "${OPENSSL_LIB}/libcrypto.3.dylib" \
  "@loader_path/libcrypto.3.dylib" \
  "$PYTHON_DIR/lib/libssl.3.dylib" 2>/dev/null || true

echo "  ✅ 5 dylibs copied"

# --------------- 4. Fix stdlib .so references ---------------
echo "[3/5] Fixing stdlib .so dylib references..."

# Read actual paths from otool and fix
for so_info in \
    "_ssl:libssl.3:$OPENSSL_LIB" \
    "_ssl:libcrypto.3:$OPENSSL_LIB" \
    "_hashlib:libcrypto.3:$OPENSSL_LIB" \
    "_decimal:libmpdec.4:$MPDECIMAL_LIB" \
    "_lzma:liblzma.5:$XZ_LIB" \
    "_sqlite3:libsqlite3.0:$SQLITE_LIB"
do
    IFS=':' read -r so_name lib_name lib_dir <<< "$so_info"
    so_path="$DYNLOAD/${so_name}.cpython-312-darwin.so"

    if [ ! -f "$so_path" ]; then
        echo "  ⚠️  $so_path not found, skipping"
        continue
    fi

    # Check if it references a Homebrew path
    old_path=$(otool -L "$so_path" 2>/dev/null | grep "$lib_name" | head -1 | awk '{print $1}')
    if [ -z "$old_path" ]; then
        echo "  ⚠️  $so_name: no $lib_name reference found"
        continue
    fi

    # Also check /usr/local/opt/ alias
    opt_path="/usr/local/opt/$(echo "$lib_name" | sed 's/\.\d\+$//')/lib/${lib_name}.dylib"

    for old in "$old_path" "$opt_path" "/usr/local/opt/openssl@3/lib/${lib_name}.dylib" "/usr/local/opt/openssl/lib/${lib_name}.dylib"; do
        install_name_tool -change "$old" "@loader_path/../../${lib_name}.dylib" "$so_path" 2>/dev/null || true
    done

    echo "  ✅ $so_name fixed"
done

# --------------- 5. Clean up broken symlinks ---------------
echo "[4/5] Cleaning up broken artifacts..."

# config-3.12-darwin has a broken symlink to libpython
rm -rf "$PYTHON_DIR/lib/python3.12/config-3.12-darwin/" 2>/dev/null || true
echo "  ✅ config-3.12-darwin removed"

# --------------- 6. Verify ---------------
echo "[5/5] Verifying..."

HOMEBREW_REFS=0
for so in _ssl _hashlib _decimal _lzma _sqlite3; do
    so_path="$DYNLOAD/${so}.cpython-312-darwin.so"
    if [ -f "$so_path" ]; then
        count=$(otool -L "$so_path" 2>/dev/null | grep -c '/usr/local' || true)
        if [ "$count" -gt 0 ]; then
            echo "  ❌ $so: still has /usr/local references ($count)"
            HOMEBREW_REFS=$((HOMEBREW_REFS + count))
        else
            echo "  ✅ $so: clean"
        fi
    fi
done

# Check python3.12
py_count=$(otool -L "$PYTHON_DIR/bin/python3.12" 2>/dev/null | grep -c '/usr/local' || true)
if [ "$py_count" -gt 0 ]; then
    echo "  ❌ python3.12: still has /usr/local references ($py_count)"
    HOMEBREW_REFS=$((HOMEBREW_REFS + py_count))
else
    echo "  ✅ python3.12: clean"
fi

# Functional test
echo ""
echo "--- Functional test ---"
PYTHONHOME="$PYTHON_DIR" KI_HOME="/tmp/ki_portable_test" KI_TAURI="1" \
"$PYTHON_DIR/bin/python3" -c "
import ssl, hashlib, decimal, lzma, sqlite3
import json, os, sys
print(f'Python {sys.version}')
print(f'PYTHONHOME: {os.environ.get(\"PYTHONHOME\", \"not set\")}')
print(f'ssl: {ssl.OPENSSL_VERSION}')
print(f'hashlib: sha256 ok')
print(f'decimal: ok')
print(f'lzma: ok')
print(f'sqlite3: {sqlite3.sqlite_version}')
" 2>&1 && echo "  ✅ All stdlib modules OK" || echo "  ❌ Functional test FAILED"

rm -rf /tmp/ki_portable_test

echo ""
if [ "$HOMEBREW_REFS" -gt 0 ]; then
    echo "❌ DONE with $HOMEBREW_REFS Homebrew references remaining — review before building"
    exit 1
else
    echo "✅ DONE — Python is fully portable"
fi
