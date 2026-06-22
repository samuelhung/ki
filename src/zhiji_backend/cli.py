"""知几后端命令行入口

命令:
  zhiji init [--data-dir ~/.zhiji]    初始化数据目录
  zhiji serve [--port 9120]            启动服务
  zhiji version                         显示版本
  zhiji update                          检查并安装更新
"""
import argparse
import sys
import os
from pathlib import Path


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
            "# DEEPSEEK_API_KEY=sk-xxx\n"
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


def cmd_update(_args: argparse.Namespace) -> None:
    """通过 pip 更新到最新版。"""
    print("更新 zhiji-backend...")
    import subprocess as sp
    sp.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "zhiji-backend"],
        check=False,
    )
    print("更新完成，请重启服务。")


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
    up_p = sub.add_parser("update", help="检查并安装更新（通过 pip）")
    up_p.set_defaults(func=cmd_update)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
