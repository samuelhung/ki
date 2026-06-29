"""知几后端命令行入口

命令:
  zhiji init [--data-dir ~/.zhiji]    初始化数据目录
  zhiji serve [--port 9120]            启动服务
  zhiji version                         显示版本
  zhiji update [--check]                检查并安装更新（GitHub Releases）
"""
import argparse
import json
import shutil
import subprocess as sp
import sys
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


GITHUB_API = "https://api.github.com/repos/samuelhung/ki/releases/latest"
LAUNCHD_LABEL = "com.zhiji.backend"


def _get_current_version() -> str:
    """读取当前版本号。"""
    from zhiji_backend import __version__
    return __version__


def _get_latest_release() -> dict | None:
    """从 GitHub API 获取最新 Release 信息。"""
    req = Request(GITHUB_API)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "zhiji-updater")
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except URLError as e:
        print(f"⚠️  无法连接 GitHub: {e}")
        return None


def _find_whl_asset(release: dict) -> dict | None:
    """从 Release assets 中找到 .whl 文件。"""
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".whl"):
            return asset
    return None


def _parse_version(tag: str) -> tuple[int, ...]:
    """从 tag 名提取版本号 (如 'v1.9.0+83' → (1,9,0,83))。"""
    v = tag.strip().lstrip("v")
    main, _, build = v.partition("+")
    main = main.split("-", 1)[0]
    parts: list[int] = []
    try:
        parts.extend(int(x) for x in main.split(".") if x != "")
        if build:
            parts.append(int(build.split(".", 1)[0]))
        return tuple(parts) if parts else (0,)
    except ValueError:
        return (0,)


def _restart_service() -> bool:
    """尝试重启 launchd 服务。"""
    try:
        # 检查 launchd 中是否有该服务
        result = sp.run(
            ["launchctl", "list", LAUNCHD_LABEL],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # 服务存在，重载
            sp.run(["launchctl", "unload", f"~/Library/LaunchAgents/{LAUNCHD_LABEL}.plist"],
                   shell=True, timeout=10)
            sp.run(["launchctl", "load", f"~/Library/LaunchAgents/{LAUNCHD_LABEL}.plist"],
                   shell=True, timeout=10)
            return True
    except Exception:
        pass
    return False


def cmd_update(args: argparse.Namespace) -> None:
    """检查 GitHub Release 并安装更新。"""
    current = _get_current_version()
    print(f"当前版本: {current}")

    release = _get_latest_release()
    if release is None:
        sys.exit(1)

    tag = release.get("tag_name", "")
    latest_version = tag.lstrip("v")
    print(f"最新版本: {latest_version}")

    if _parse_version(tag) <= _parse_version(f"v{current}"):
        print("✅ 已是最新版本。")
        return

    if args.check:
        print(f"\n📦 有新版本可用: {latest_version}")
        print(f"   运行 zhiji update 安装更新。")
        return

    # 找 whl
    whl = _find_whl_asset(release)
    if whl is None:
        print("❌ Release 中没有找到 .whl 文件。")
        sys.exit(1)

    download_url = whl["browser_download_url"]
    filename = whl["name"]
    size_mb = whl.get("size", 0) / (1024 * 1024)

    print(f"\n⬇️  下载 {filename} ({size_mb:.1f} MB)...")

    # 下载到临时目录
    tmpdir = tempfile.mkdtemp(prefix="zhiji_update_")
    tmp_whl = os.path.join(tmpdir, filename)

    try:
        req = Request(download_url)
        req.add_header("Accept", "application/octet-stream")
        req.add_header("User-Agent", "zhiji-updater")
        with urlopen(req, timeout=300) as resp:
            with open(tmp_whl, "wb") as f:
                shutil.copyfileobj(resp, f)
        print(f"✅ 下载完成")
    except URLError as e:
        print(f"❌ 下载失败: {e}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    # pip install
    print(f"\n📦 安装 {filename}...")
    result = sp.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", tmp_whl],
        capture_output=False, timeout=120,
    )

    # 清理
    shutil.rmtree(tmpdir, ignore_errors=True)

    if result.returncode != 0:
        print("❌ 安装失败，请手动更新。")
        sys.exit(1)

    print(f"✅ 已更新到 {latest_version}")

    # 尝试重启服务
    if _restart_service():
        print("✅ 服务已自动重启。")
    else:
        print("⚠️  请手动重启服务: zhiji serve")


def cmd_init(args: argparse.Namespace) -> None:
    """初始化数据目录 — 创建 ~/.zhiji/ 及所有子目录。幂等，可多次执行。"""
    home = Path(args.data_dir).expanduser().resolve() if args.data_dir else Path.home() / ".zhiji"
    os.environ["ZHIJI_HOME"] = str(home)

    from zhiji_backend.paths import ensure_data_dirs, ZHIJI_HOME, DATA_DIR, LOG_DIR
    from zhiji_backend.paths import INGEST_ROOT, BRAINSTORM_DIR, STUDY_DATA_DIR
    from zhiji_backend.paths import CONFIG_PATH

    ensure_data_dirs()

    print(f"知几数据目录: {ZHIJI_HOME}")
    print(f"  数据: {DATA_DIR}")
    print(f"  日志: {LOG_DIR}")
    print(f"  采集: {INGEST_ROOT}")
    print(f"  脑暴: {BRAINSTORM_DIR}")
    print(f"  学习: {STUDY_DATA_DIR}")

    # 创建默认 .env 模板（如果不存在）
    env_path = ZHIJI_HOME / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# 知几配置文件 — 在此设置 API Key\n"
            "# AI_API_KEY=sk-xxx\n"
            "# OPENAI_API_KEY=sk-xxx\n"
            "# DEEPSEEK_API_KEY=sk-xxx  # 兼容旧版本，可不填\n"
            "# KI_API_TOKEN=your-secret-token\n"
        )
        print(f"  已创建默认配置: {env_path}")
    else:
        print(f"  .env 已存在，跳过: {env_path}")

    # 创建默认系统配置（如果不存在）
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text('{"version": "1.0", "sources": []}', encoding="utf-8")
        print(f"  已创建默认系统配置: {CONFIG_PATH}")
    else:
        print(f"  系统配置已存在，跳过: {CONFIG_PATH}")

    print("\n✅ 初始化完成。运行 zhiji serve 启动服务。")


def cmd_serve(args: argparse.Namespace) -> None:
    """启动 FastAPI 服务。"""
    if args.data_dir:
        os.environ["ZHIJI_HOME"] = args.data_dir
    elif not os.getenv("ZHIJI_HOME"):
        # 默认 ~/.zhiji/，如果不存在则自动初始化
        default = str(Path.home() / ".zhiji")
        os.environ["ZHIJI_HOME"] = default

        # 自动初始化数据目录
        from zhiji_backend.paths import ensure_data_dirs
        ensure_data_dirs()

    import uvicorn
    uvicorn.run(
        "zhiji_backend.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )


def cmd_version(_args: argparse.Namespace) -> None:
    """显示版本号。"""
    from zhiji_backend import __version__
    print(f"zhiji-backend {__version__}")


def main() -> None:
    parser = argparse.ArgumentParser(description="知几 —— 个人情报中心后端")
    sub = parser.add_subparsers(dest="command")

    # zhiji init
    init_p = sub.add_parser("init", help="初始化数据目录 (~/.zhiji/)")
    init_p.add_argument("--data-dir", default=None, help="数据目录，默认 ~/.zhiji/")
    init_p.set_defaults(func=cmd_init)

    # zhiji serve
    serve_p = sub.add_parser("serve", help="启动服务")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=9120)
    serve_p.add_argument("--data-dir", default=None, help="数据目录，默认 ~/.zhiji/")
    serve_p.set_defaults(func=cmd_serve)

    # zhiji version
    ver_p = sub.add_parser("version", help="显示版本")
    ver_p.set_defaults(func=cmd_version)

    # zhiji update
    up_p = sub.add_parser("update", help="检查并安装更新（从 GitHub Releases）")
    up_p.add_argument("--check", action="store_true", help="仅检查，不安装")
    up_p.set_defaults(func=cmd_update)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
