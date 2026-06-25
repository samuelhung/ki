#!/usr/bin/env python3
"""
知几发版前诊断 — 验证签名、appcast、后端分发全链路
用法: python3 scripts/release-check.py [version]
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP = PROJECT_ROOT / "desktop"
APPCAST = PROJECT_ROOT / "appcast.xml"
FLUTTER_APP = DESKTOP / "build" / "macos" / "Build" / "Products" / "Release" / "知几.app"
RELEASES_DIR = Path.home() / ".zhiji" / "data" / "releases"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
NC = "\033[0m"

errors = []

def ok(msg): print(f"  {GREEN}✓{NC} {msg}")
def fail(msg): print(f"  {RED}✗{NC} {msg}"); errors.append(msg)
def warn(msg): print(f"  {YELLOW}⚠{NC} {msg}")

def check(label: str) -> None:
    print(f"\n{GREEN}{'━'*60}{NC}")
    print(f"  {label}")
    print(f"{GREEN}{'━'*60}{NC}")

# ── 1. 编译产物 ──
check("1. 编译产物")
if FLUTTER_APP.exists():
    ok(f"知几.app: {FLUTTER_APP}")
else:
    fail(f"知几.app 不存在: {FLUTTER_APP}")
    print("  请先运行: cd desktop && flutter build macos")
    sys.exit(1)

# ── 2. 代码签名 ──
check("2. 代码签名（必须 Authority=Zhiji，不能 adhoc）")
try:
    r = subprocess.run(["codesign", "-dvvv", str(FLUTTER_APP)], capture_output=True, text=True, timeout=10)
    if "Authority=Zhiji" in r.stdout:
        ok(".app: Authority=Zhiji")
    elif "Signature=adhoc" in r.stdout:
        fail(".app: Signature=adhoc（未签名！）")
    else:
        warn(f".app: 无法确定签名状态")

    auto = FLUTTER_APP / "Contents/Frameworks/Sparkle.framework/Versions/B/Autoupdate"
    if auto.exists():
        r2 = subprocess.run(["codesign", "-dvvv", str(auto)], capture_output=True, text=True, timeout=10)
        if "Authority=Zhiji" in r2.stdout:
            ok("Sparkle Autoupdate: Authority=Zhiji")
        else:
            fail("Sparkle Autoupdate: 未签名或签名无效")
    else:
        fail("Sparkle Autoupdate 不存在")
except Exception as e:
    fail(f"签名检查失败: {e}")

# ── 3. Info.plist ──
check("3. Info.plist Sparkle 配置")
plist = FLUTTER_APP / "Contents/Info.plist"
if plist.exists():
    try:
        r = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print :SUEnableInstallerLauncherService", str(plist)], capture_output=True, text=True)
        if "false" in r.stdout:
            ok("SUEnableInstallerLauncherService = false ✓")
        else:
            fail("SUEnableInstallerLauncherService 不是 false")
    except: fail("SUEnableInstallerLauncherService 缺失")

    try:
        r = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print :SUFeedURL", str(plist)], capture_output=True, text=True)
        url = r.stdout.strip()
        if "samuelhung/ki" in url and "appcast.xml" in url:
            ok(f"SUFeedURL: {url}")
        else:
            warn(f"SUFeedURL 异常: {url}")
    except: fail("SUFeedURL 缺失")

    try:
        r = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print :SUPublicEDKey", str(plist)], capture_output=True, text=True)
        key = r.stdout.strip()
        if len(key) >= 40:
            ok(f"SUPublicEDKey: {key[:16]}...")
        else:
            fail("SUPublicEDKey 无效")
    except: fail("SUPublicEDKey 缺失")
else:
    fail("Info.plist 不存在")

# ── 4. DMG 完整性 ──
check("4. DMG 完整性")
dmg_files = sorted(DESKTOP.glob("build/release/zhiji_*.dmg"), key=lambda p: p.stat().st_mtime, reverse=True)
if dmg_files:
    dmg = dmg_files[0]
    ver = re.search(r'zhiji_(.*?)\.dmg', dmg.name)
    ver_str = ver.group(1) if ver else "?"
    size = dmg.stat().st_size / (1024*1024)
    ok(f"DMG: {dmg.name} ({size:.1f} MB)")

    try:
        r = subprocess.run(["codesign", "-dvvv", str(dmg)], capture_output=True, text=True, timeout=10)
        if "Authority=Zhiji" in r.stdout:
            ok("DMG: Authority=Zhiji")
        else:
            fail("DMG: 签名无效")
    except: fail("DMG 签名检查失败")
else:
    fail("未找到 DMG 文件")

# ── 5. appcast.xml ──
check("5. appcast.xml")
if APPCAST.exists():
    content = APPCAST.read_text()
    items = re.findall(r'<item>.*?</item>', content, re.DOTALL)
    ok(f"条目数: {len(items)}")

    if items:
        first = items[0]
        for key in ['sparkle:shortVersionString', 'sparkle:version', 'url', 'sparkle:edSignature']:
            m = re.search(rf'{key}="([^"]+)"', first)
            if m:
                val = m.group(1)
                if key == 'sparkle:edSignature':
                    ok(f"{key}: {val[:30]}...")
                else:
                    ok(f"{key}: {val}")
            else:
                fail(f"{key}: 缺失")

        # Check URL is backend
        url_m = re.search(r'url="([^"]+)"', first)
        if url_m:
            url = url_m.group(1)
            if "10.8.0.105" in url:
                ok("下载 URL: 后端内网 ✓")
            elif "github.com" in url:
                warn("下载 URL: GitHub（中国下载慢，可能超时）")
else:
    fail("appcast.xml 不存在")

# ── 6. 后端分发 ──
check("6. 后端 DMG 分发")
if dmg_files:
    backend_path = RELEASES_DIR / dmg_files[0].name
    if backend_path.exists():
        bsize = backend_path.stat().st_size
        dsize = dmg_files[0].stat().st_size
        if bsize == dsize:
            ok(f"后端 DMG: {backend_path} ({bsize/(1024*1024):.1f} MB) 与构建一致")
        else:
            fail(f"后端 DMG 大小不一致（构建:{dsize} 后端:{bsize}）")
    else:
        warn(f"后端 DMG 不存在，运行 build_release.py 会自动拷贝")

    # 测试后端 HTTP
    import urllib.request
    dmg_name = dmg_files[0].name
    try:
        req = urllib.request.Request(f"http://127.0.0.1:9120/releases/{dmg_name}", method="HEAD")
        resp = urllib.request.urlopen(req, timeout=5)
        if resp.status == 200:
            ok(f"后端 HTTP 可达: /releases/{dmg_name} (200)")
        else:
            warn(f"后端 HTTP: {resp.status}")
    except Exception as e:
        warn(f"后端 HTTP 检查失败: {e}（需重启后端加载新路由）")

# ── 7. 证书 ──
check("7. 代码签名证书")
try:
    r = subprocess.run(["security", "find-certificate", "-c", "Zhiji", "-p"], capture_output=True, text=True, timeout=5)
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as f:
        f.write(r.stdout.encode()); f.flush()
        r2 = subprocess.run(["openssl", "x509", "-noout", "-dates", "-in", f.name], capture_output=True, text=True)
        os.unlink(f.name)
    ok(f"证书: {r2.stdout.strip()}")
except: fail("证书检查失败")

# ── 总结 ──
check("诊断总结")
if errors:
    print(f"\n  {RED}发现 {len(errors)} 个问题:{NC}")
    for e in errors:
        print(f"  {RED}✗{NC} {e}")
    sys.exit(1)
else:
    print(f"\n  {GREEN}🎉 全部通过！可以安全发版。{NC}")
