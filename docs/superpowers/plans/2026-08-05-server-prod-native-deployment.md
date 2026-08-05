# server-prod 原生部署与迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立版本化 wheel + systemd 的非 Docker 正式部署工具，并用该工具把空数据库的新正式环境迁移到 `server-prod`。

**Architecture:** 保留 `deploy_backend.py` 中经过验证的制品校验、版本安装、SQLite 备份、原子切换和失败回滚核心，通过注入服务准备器适配 systemd。新增本地部署编排器负责 `origin/main` 门禁、固定环境构建、SCP 暂存和简短摘要；新增一次性远端 provisioner 负责非 root 用户、项目工具链、目录、systemd 和 UFW。

**Tech Stack:** Python 3.12、uv、pytest、POSIX shell、SSH/SCP、systemd、UFW、SQLite、FFmpeg、Node 22.17.0、npm、Vite

---

## 文件结构

- `src/zhiji_backend/paths.py`：统一解析 `ZHIJI_HOME` 和可选的 `KI_ENV_FILE`。
- `src/zhiji_backend/main.py`、`credential_store.py`、`cli.py`：统一使用解析后的环境文件路径。
- `scripts/deploy_backend.py`：保留跨平台部署核心和 launchd 兼容入口，允许注入服务定义准备器。
- `scripts/deploy_backend_systemd.py`：systemd 控制器、Linux 路径策略和远端部署 CLI。
- `scripts/production_target.py`：固定生产目标、SSH/SCP 执行、输出脱敏和来源 SHA 门禁。
- `scripts/provision_backend_systemd.py`：在 Linux 主机上执行幂等初始化。
- `scripts/provision_production.py`：本地一次性初始化编排入口。
- `scripts/deploy_production.py`：本地日常构建、上传、部署和摘要入口。
- `scripts/provision-production`、`scripts/deploy-production`：面向操作者的薄 shell 入口。
- `tests/test_systemd_backend_deploy.py`：systemd 单元和控制器测试。
- `tests/test_provision_backend_systemd.py`：远端初始化的目录、权限、UFW 和幂等测试。
- `tests/test_production_target.py`：主机身份、Git 门禁、脱敏和命令封装测试。
- `tests/test_production_orchestration.py`：初始化与日常发布的端到端编排测试。

### Task 1: 支持独立的服务端环境文件

**Files:**
- Modify: `src/zhiji_backend/paths.py`
- Modify: `src/zhiji_backend/main.py`
- Modify: `src/zhiji_backend/credential_store.py`
- Modify: `src/zhiji_backend/cli.py`
- Modify: `tests/test_system_config_security.py`
- Modify: `tests/test_access_security.py`

- [ ] **Step 1: 写入环境文件路径失败测试**

在 `tests/test_system_config_security.py` 增加隔离子进程测试，断言显式路径优先且配置更新写回该文件：

```python
def test_explicit_env_file_is_authoritative(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env_file = tmp_path / "etc" / "zhiji.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("KI_API_TOKEN=external-token\n", encoding="utf-8")
    env_file.chmod(0o600)

    result = _run_isolated(
        "from zhiji_backend.paths import ENV_PATH; print(ENV_PATH)",
        ZHIJI_HOME=str(home),
        KI_ENV_FILE=str(env_file),
    )

    assert result.stdout.strip() == str(env_file.resolve())
    assert not (home / ".env").exists()
```

在 `tests/test_access_security.py` 增加相对路径拒绝测试：

```python
def test_relative_explicit_env_file_is_rejected(tmp_path: Path) -> None:
    result = _run_isolated(
        "import zhiji_backend.paths",
        ZHIJI_HOME=str(tmp_path),
        KI_ENV_FILE="relative.env",
        check=False,
    )
    assert result.returncode != 0
    assert "KI_ENV_FILE must be absolute" in result.stderr
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest \
  tests/test_system_config_security.py::test_explicit_env_file_is_authoritative \
  tests/test_access_security.py::test_relative_explicit_env_file_is_rejected -q
```

Expected: FAIL，`ENV_PATH` 尚不存在，且相对路径尚未被拒绝。

- [ ] **Step 3: 实现唯一环境文件路径解析**

在 `src/zhiji_backend/paths.py` 增加：

```python
def _get_env_path(home: Path) -> Path:
    configured = os.getenv("KI_ENV_FILE", "").strip()
    if not configured:
        return home / ".env"
    path = Path(configured).expanduser()
    if not path.is_absolute():
        raise RuntimeError("KI_ENV_FILE must be absolute")
    return path.resolve()


ZHIJI_HOME = _get_zhiji_home()
ENV_PATH = _get_env_path(ZHIJI_HOME)
```

将 `main.py`、`credential_store.py` 和 `cli.py` 中自行拼接的
`ZHIJI_HOME / ".env"` 替换为从 `paths` 导入的 `ENV_PATH`。保持没有
`KI_ENV_FILE` 时的桌面端和旧 Mac 行为完全不变。

- [ ] **Step 4: 运行相关安全测试**

Run:

```bash
uv run --frozen pytest \
  tests/test_system_config_security.py \
  tests/test_access_security.py \
  tests/test_backend_smoke.py -q
```

Expected: PASS，旧默认路径与新显式路径均通过。

- [ ] **Step 5: 提交**

```bash
git add src/zhiji_backend/paths.py src/zhiji_backend/main.py \
  src/zhiji_backend/credential_store.py src/zhiji_backend/cli.py \
  tests/test_system_config_security.py tests/test_access_security.py
git commit -m "feat: support external server environment file"
```

### Task 2: 将服务定义准备从原子部署核心中解耦

**Files:**
- Modify: `scripts/deploy_backend.py`
- Modify: `tests/test_backend_deploy.py`

- [ ] **Step 1: 写入服务准备器注入测试**

在 `tests/test_backend_deploy.py` 增加：

```python
def test_deploy_uses_injected_service_preparer(tmp_path: Path) -> None:
    config = _config(tmp_path)
    prepared: list[BackendDeployConfig] = []

    deploy_backend(
        config,
        service=FakeService(),
        installer=_install,
        prepare_service=prepared.append,
        smoke_check=lambda: None,
    )

    assert prepared == [config]
    assert not config.launchd_plist.exists()


def test_service_prepare_failure_happens_before_stop(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = FakeService()

    with pytest.raises(RuntimeError, match="unit invalid"):
        deploy_backend(
            config,
            service=service,
            installer=_install,
            prepare_service=lambda _config: (_ for _ in ()).throw(
                RuntimeError("unit invalid")
            ),
            smoke_check=lambda: None,
        )

    assert service.events == []
    assert not config.current_link.exists()
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_backend_deploy.py \
  -k 'injected_service_preparer or service_prepare_failure' -q
```

Expected: FAIL，`deploy_backend()` 尚不接受 `prepare_service`。

- [ ] **Step 3: 增加兼容注入点**

将核心签名扩展为：

```python
def deploy_backend(
    config: BackendDeployConfig,
    *,
    service: ServiceController,
    smoke_check: Callable[[], None],
    rollback_smoke_check: Callable[[], None] | None = None,
    installer: Callable[[Path, BackendDeployConfig], None] = _default_installer,
    prepare_service: Callable[[BackendDeployConfig], None] = write_launchd_plist,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Path:
```

将 `_deploy_backend_locked()` 中的 `write_launchd_plist(config)` 改为
`prepare_service(config)`，并把参数完整向下传递。launchd CLI 不传该参数，
因此保持原行为。

- [ ] **Step 4: 运行部署器完整测试**

Run:

```bash
uv run --frozen pytest tests/test_backend_deploy.py -q
```

Expected: PASS，现有 launchd、备份、回滚和保留历史测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add scripts/deploy_backend.py tests/test_backend_deploy.py
git commit -m "refactor: inject backend service preparation"
```

### Task 3: 增加 systemd 部署适配器

**Files:**
- Create: `scripts/deploy_backend_systemd.py`
- Create: `tests/test_systemd_backend_deploy.py`
- Modify: `scripts/deploy_backend.py`

- [ ] **Step 1: 写入 systemd 控制与路径策略测试**

创建 `tests/test_systemd_backend_deploy.py`，覆盖以下核心契约：

```python
def test_systemd_controller_uses_noninteractive_sudo() -> None:
    calls: list[list[str]] = []
    controller = SystemdServiceController(run=lambda command, **_: calls.append(command))
    controller.stop()
    controller.start()
    assert calls == [
        ["sudo", "-n", "/usr/bin/systemctl", "stop", "zhiji.service"],
        ["sudo", "-n", "/usr/bin/systemctl", "start", "zhiji.service"],
    ]


def test_systemd_layout_uses_separate_program_and_data_disks(tmp_path: Path) -> None:
    config = _linux_config(tmp_path)
    assert config.backend.runtime_root == tmp_path / "srv/apps/zhiji"
    assert config.backend.zhiji_home == tmp_path / "data/apps/zhiji"
    assert config.backend.database_path == tmp_path / "data/apps/zhiji/data/intelligence.sqlite"
    assert config.backend.backups_dir == tmp_path / "data/backups/zhiji"


def test_systemd_preparer_rejects_wrong_exec_start(tmp_path: Path) -> None:
    config = _linux_config(tmp_path)
    config.service_definition.write_text("ExecStart=/bin/false\n", encoding="utf-8")
    with pytest.raises(BackendDeployError, match="systemd unit ExecStart"):
        validate_systemd_service(config)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_systemd_backend_deploy.py -q
```

Expected: FAIL，systemd 模块尚不存在。

- [ ] **Step 3: 实现 Linux 配置和控制器**

在 `scripts/deploy_backend.py` 的 `BackendDeployConfig` 增加带兼容默认值的字段：

```python
application_root: Path | None = None
env_file: Path | None = None

@property
def packages_dir(self) -> Path:
    return (self.application_root or self.zhiji_home) / "packages"

@property
def effective_env_file(self) -> Path:
    return self.env_file or self.zhiji_home / ".env"
```

让制品父目录校验使用 `packages_dir`，远程绑定校验使用
`effective_env_file`。当 `application_root is None` 时继续执行现有 launchd
路径约束；当它存在时要求 `runtime_root == application_root`、制品位于
`application_root/packages` 下的 40 位十六进制来源 SHA 子目录、数据库位于
`zhiji_home/data/intelligence.sqlite`，并允许独立的绝对备份目录和 systemd
单元路径。launchd 的默认值继续得到旧路径。

创建 `scripts/deploy_backend_systemd.py`，定义：

```python
@dataclass(frozen=True)
class SystemdDeployConfig:
    backend: BackendDeployConfig
    service_definition: Path = Path("/etc/systemd/system/zhiji.service")
    service_name: str = "zhiji.service"


class SystemdServiceController:
    def __init__(self, *, run=subprocess.run) -> None:
        self._run = run

    def stop(self) -> None:
        self._run(
            ["sudo", "-n", "/usr/bin/systemctl", "stop", "zhiji.service"],
            check=True,
        )

    def start(self) -> None:
        self._run(
            ["sudo", "-n", "/usr/bin/systemctl", "start", "zhiji.service"],
            check=True,
        )
```

CLI 固定正式路径，只接受发布标签、wheel 和校验清单等非秘密参数；禁止任何
token 参数。调用 `deploy_backend(..., prepare_service=validate_systemd_service,
preserve_history=True)` 时使用闭包保持类型一致：

```python
deploy_backend(
    systemd_config.backend,
    service=SystemdServiceController(),
    prepare_service=lambda _backend: validate_systemd_service(systemd_config),
    smoke_check=lambda: default_smoke_check("http://127.0.0.1:9120"),
)
```

- [ ] **Step 4: 运行 Linux 与旧 Mac 部署测试**

Run:

```bash
uv run --frozen pytest \
  tests/test_systemd_backend_deploy.py \
  tests/test_backend_deploy.py -q
```

Expected: PASS，Linux 路径通过，launchd 兼容测试无回归。

- [ ] **Step 5: 提交**

```bash
git add scripts/deploy_backend.py scripts/deploy_backend_systemd.py \
  tests/test_backend_deploy.py tests/test_systemd_backend_deploy.py
git commit -m "feat: add systemd backend deployment adapter"
```

### Task 4: 建立生产目标与安全命令层

**Files:**
- Create: `scripts/production_target.py`
- Create: `tests/test_production_target.py`

- [ ] **Step 1: 写入目标、Git 与脱敏测试**

创建 `tests/test_production_target.py`：

```python
def test_production_target_is_fixed() -> None:
    assert TARGET.admin_ssh_host == "server-prod"
    assert TARGET.ssh_destination == "zhiji@10.8.0.45"
    assert TARGET.overlay_ip == "10.8.0.45"
    assert TARGET.lan_ip == "192.168.100.163"
    assert TARGET.port == 9120


def test_source_gate_requires_pushed_origin_main() -> None:
    git = FakeGit(
        head="a" * 40,
        origin_main="a" * 40,
        branch="codex/release",
        dirty="",
    )
    assert verify_source(git) == "a" * 40


def test_source_gate_rejects_unpushed_commit() -> None:
    git = FakeGit(head="b" * 40, origin_main="a" * 40, branch="main", dirty="")
    with pytest.raises(ProductionDeployError, match="origin/main"):
        verify_source(git)


def test_summary_never_contains_secret_values() -> None:
    text = render_summary(
        status="PASS", tag="v2.0.0+112", source_sha="a" * 40,
        duration_seconds=214, url="http://10.8.0.45:9120",
    )
    assert "PASS" in text
    assert "token" not in text.lower()
    assert "api_key" not in text.lower()
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_production_target.py -q
```

Expected: FAIL，生产目标模块尚不存在。

- [ ] **Step 3: 实现固定目标和列表参数执行器**

`production_target.py` 使用不可变数据类保存目标，不允许通过普通 CLI 参数覆盖：

```python
@dataclass(frozen=True)
class ProductionTarget:
    admin_ssh_host: str = "server-prod"
    ssh_destination: str = "zhiji@10.8.0.45"
    expected_hostname: str = "server"
    expected_user: str = "zhiji"
    overlay_ip: str = "10.8.0.45"
    lan_ip: str = "192.168.100.163"
    port: int = 9120
    application_root: PurePosixPath = PurePosixPath("/srv/apps/zhiji")
    data_root: PurePosixPath = PurePosixPath("/data/apps/zhiji")
    backups_root: PurePosixPath = PurePosixPath("/data/backups/zhiji")


TARGET = ProductionTarget()
```

所有本地子进程使用参数列表和 `check=True`；SSH 远端命令由固定模板生成，动态
值仅允许通过发布标签、40 位十六进制 SHA 和经过 `shlex.quote()` 的本地路径。
错误摘要只保留退出码和阶段名，不转储环境或完整 stderr。

- [ ] **Step 4: 运行测试**

Run:

```bash
uv run --frozen pytest tests/test_production_target.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/production_target.py tests/test_production_target.py
git commit -m "feat: define locked production deployment target"
```

### Task 5: 实现幂等 Linux 初始化器

**Files:**
- Create: `scripts/provision_backend_systemd.py`
- Create: `tests/test_provision_backend_systemd.py`

- [ ] **Step 1: 写入初始化计划测试**

测试使用临时根目录和假命令执行器，不调用真实 `useradd`、systemctl 或 UFW：

```python
def test_provision_plan_separates_program_data_and_secrets(tmp_path: Path) -> None:
    config = _config_under(tmp_path)
    provision(config, runner=FakeRootRunner(), toolchains=FakeToolchains())
    assert config.application_root.is_dir()
    assert config.data_root.is_dir()
    assert config.backups_root.is_dir()
    assert stat.S_IMODE(config.env_file.stat().st_mode) == 0o600
    assert config.unit_file.read_text(encoding="utf-8").count("User=zhiji") == 1


def test_provision_is_idempotent(tmp_path: Path) -> None:
    config = _config_under(tmp_path)
    runner = FakeRootRunner()
    provision(config, runner=runner, toolchains=FakeToolchains())
    first = _tree_digest(tmp_path)
    provision(config, runner=runner, toolchains=FakeToolchains())
    assert _tree_digest(tmp_path) == first


def test_provision_creates_valid_empty_sqlite_database(tmp_path: Path) -> None:
    config = _config_under(tmp_path)
    provision(config, runner=FakeRootRunner(), toolchains=FakeToolchains())
    with sqlite3.connect(config.database_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0] == 0


def test_ufw_rules_allow_only_confirmed_networks() -> None:
    assert render_ufw_commands() == [
        ["ufw", "allow", "from", "10.8.0.0/24", "to", "any", "port", "9120", "proto", "tcp", "comment", "zhiji-overlay"],
        ["ufw", "allow", "from", "192.168.100.0/24", "to", "any", "port", "9120", "proto", "tcp", "comment", "zhiji-lan"],
    ]
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_provision_backend_systemd.py -q
```

Expected: FAIL，初始化模块尚不存在。

- [ ] **Step 3: 实现目录、工具链、systemd 与 sudoers 初始化**

初始化器要求 root 并执行以下固定契约：

```text
user: zhiji, home=/srv/apps/zhiji, shell=/bin/bash
program owner: zhiji:zhiji, mode 0750
data owner: zhiji:zhiji, mode 0750
env owner: zhiji:zhiji, mode 0600
Python: uv-managed CPython 3.12.13
uv: 0.8.13
FFmpeg: imageio-ffmpeg 0.6.0 bundled binary exposed at toolchains/ffmpeg/bin/ffmpeg
```

systemd 单元必须生成以下关键内容：

```ini
[Service]
User=zhiji
Group=zhiji
WorkingDirectory=/data/apps/zhiji
Environment=ZHIJI_HOME=/data/apps/zhiji
Environment=KI_ENV_FILE=/etc/zhiji/zhiji.env
Environment=PATH=/srv/apps/zhiji/toolchains/ffmpeg/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
EnvironmentFile=/etc/zhiji/zhiji.env
ExecStart=/srv/apps/zhiji/current/venv/bin/python -m zhiji_backend.cli serve --host 0.0.0.0 --port 9120
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/data/apps/zhiji /data/backups/zhiji
```

sudoers 只授权 `zhiji` 非交互执行 `systemctl start/stop/is-active
zhiji.service`。写入前用 `visudo -cf` 校验临时文件，成功后原子替换。

初始化器还要使用 Python `sqlite3` 创建
`/data/apps/zhiji/data/intelligence.sqlite`，执行 `PRAGMA quick_check` 并设置
`0600`。数据库只包含 SQLite 文件头，不预建业务表；首次应用启动负责现有的
schema 初始化。这样原子部署器在第一次切换前也能创建一致性备份。

- [ ] **Step 4: 运行初始化器测试**

Run:

```bash
uv run --frozen pytest tests/test_provision_backend_systemd.py -q
```

Expected: PASS，第二次运行不改变文件树，UFW 不出现宽泛规则。

- [ ] **Step 5: 提交**

```bash
git add scripts/provision_backend_systemd.py tests/test_provision_backend_systemd.py
git commit -m "feat: provision native systemd production runtime"
```

### Task 6: 实现一次性本地初始化入口

**Files:**
- Create: `scripts/provision_production.py`
- Create: `scripts/provision-production`
- Modify: `tests/test_production_orchestration.py`

- [ ] **Step 1: 写入 dry-run、确认和上传测试**

创建 `tests/test_production_orchestration.py` 并增加：

```python
def test_provision_requires_exact_confirmation() -> None:
    runner = FakeRemoteRunner(confirm="wrong-host")
    with pytest.raises(ProductionDeployError, match="confirmation"):
        provision_production(runner=runner)
    assert runner.mutations == []


def test_provision_uploads_helper_before_root_execution() -> None:
    runner = FakeRemoteRunner(confirm="server-prod 10.8.0.45")
    provision_production(runner=runner)
    assert runner.events[:3] == [
        "identity-preflight",
        "upload-provision-helper",
        "execute-provision-helper-as-root",
    ]


def test_provision_migrates_allowlisted_config_without_printing_values(
    tmp_path: Path,
    capsys,
) -> None:
    sentinel = "sentinel-volc-secret"
    runner = FakeRemoteRunner(
        confirm="server-prod 10.8.0.45",
        legacy_env=f"VOLC_API_KEY={sentinel}\nOTHER=not-migrated\n",
    )
    provision_production(runner=runner, token_file=tmp_path / "token")
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err
    assert b"VOLC_API_KEY=" in runner.new_env_payload
    assert b"OTHER=" not in runner.new_env_payload
    assert stat.S_IMODE((tmp_path / "token").stat().st_mode) == 0o600
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_production_orchestration.py \
  -k provision -q
```

Expected: FAIL，本地初始化入口尚不存在。

- [ ] **Step 3: 实现一次性入口和薄 shell 包装**

`provision_production.py` 先使用现有 `server-prod` root SSH 做只读身份核验，再
要求操作者输入完整字符串 `server-prod 10.8.0.45`。确认后上传远端 helper，
执行初始化，安装现有本地公钥，最后以固定目标 `zhiji@10.8.0.45` 重新连接并
验证。脚本不改写已有 `server-prod` SSH 别名。

初始化器随后从旧 `zhiji-prod` 的环境文件读取以下固定白名单，不复制其他键：

```python
MIGRATED_ENV_KEYS = (
    "AI_BASE_URL",
    "AI_API_KEY",
    "VOLC_API_KEY",
    "VOLC_RESOURCE_ID",
    "VOLC_MODEL_NAME",
    "TOS_AK",
    "TOS_SK",
    "TOS_ENDPOINT",
    "TOS_REGION",
    "TOS_BUCKET",
)
```

它使用 `secrets.token_urlsafe(48)` 生成新的 `KI_API_TOKEN`，固定写入
`KI_ALLOWED_HOSTS=10.8.0.45,192.168.100.163,127.0.0.1,localhost`。配置内容
只经受控子进程 stdin 写入 `/etc/zhiji/zhiji.env`，任何 stdout、stderr、异常
或摘要都不得包含值。新令牌另存到本机 `~/.config/zhiji/server-prod-token`，
文件权限 `0600`；命令只打印该路径，供操作者自行在终端读取并输入浏览器。

`scripts/provision-production` 内容固定为：

```sh
#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/provision_production.py" "$@"
```

只允许 `--dry-run` 和 `--help`，不允许通过参数替换主机、IP、用户、路径或密钥。

- [ ] **Step 4: 运行入口测试**

Run:

```bash
uv run --frozen pytest tests/test_production_orchestration.py -k provision -q
sh -n scripts/provision-production
```

Expected: PASS，shell 语法有效。

- [ ] **Step 5: 提交**

```bash
git add scripts/provision_production.py scripts/provision-production \
  tests/test_production_orchestration.py
git commit -m "feat: add one-time production provision command"
```

### Task 7: 实现日常一键部署编排器

**Files:**
- Create: `scripts/deploy_production.py`
- Create: `scripts/deploy-production`
- Modify: `tests/test_production_orchestration.py`

- [ ] **Step 1: 写入成功顺序、失败停止和版本推导测试**

在 `tests/test_production_orchestration.py` 增加：

```python
def test_deploy_runs_verified_pipeline_in_order() -> None:
    runner = FakeDeployRunner(remote_versions=["2.0.0+110", "2.0.0+111"])
    result = deploy_production(runner=runner, clock=FakeClock())
    assert result.tag == "v2.0.0+112"
    assert runner.events == [
        "verify-origin-main",
        "remote-preflight",
        "run-focused-tests",
        "build-wheel",
        "stage-sha-directory",
        "upload-artifacts",
        "verify-checksums",
        "build-linux-wheelhouse",
        "atomic-systemd-deploy",
        "postflight",
        "stability-observation",
    ]


def test_bad_checksum_never_stops_service() -> None:
    runner = FakeDeployRunner(checksum_ok=False)
    with pytest.raises(ProductionDeployError, match="checksum"):
        deploy_production(runner=runner, clock=FakeClock())
    assert "atomic-systemd-deploy" not in runner.events


def test_existing_release_number_is_never_reused() -> None:
    runner = FakeDeployRunner(remote_versions=["2.0.0+112"])
    assert next_release_tag("2.0.0", runner.remote_versions()) == "v2.0.0+113"
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_production_orchestration.py -k deploy -q
```

Expected: FAIL，日常编排器尚不存在。

- [ ] **Step 3: 实现固定流水线**

`deploy_production.py` 必须：

1. `git fetch origin main` 后比较 `HEAD`、`origin/main` 和制品相关工作区状态。
2. 从当前版本 `2.0.0` 与远端版本目录推导下一个 build number。
3. 使用固定项目 Python 3.12、Node 22.17.0、uv 与任务专用 npm 缓存运行：

```bash
uv run --frozen pytest \
  tests/test_backend_deploy.py \
  tests/test_systemd_backend_deploy.py \
  tests/test_production_target.py \
  tests/test_production_orchestration.py -q
```

4. 调用现有 `build_backend_wheel.py`，生成 wheel、`requirements.lock` 和
   `BOOTSTRAP_SHA256SUMS`。
5. 上传 `deploy_backend.py`、`deploy_backend_systemd.py`、
   `build_remote_wheelhouse.py`、`backend-build-requirements.lock`、wheel 和
   `BOOTSTRAP_SHA256SUMS` 到 SHA 暂存目录。
6. 远端先验 bootstrap 清单，再构建 Linux wheelhouse，再验最终
   `SHA256SUMS`，最后运行 systemd 部署器并强制保留历史。
7. postflight 检查 release.json、SQLite、systemd、PID、端口和健康接口。
8. 将 35 秒稳定观察与操作者页面验收并行，不在终端逐秒打印。

`scripts/deploy-production` 与 Task 6 使用相同薄包装模式。命令成功只打印：

```text
PASS version=2.0.0+112
git_sha=0123456789abcdef0123456789abcdef01234567
target=server-prod
duration=3m34s
url=http://10.8.0.45:9120
lan_url=http://192.168.100.163:9120
```

- [ ] **Step 4: 运行编排测试和 shell 检查**

Run:

```bash
uv run --frozen pytest \
  tests/test_production_target.py \
  tests/test_production_orchestration.py -q
sh -n scripts/deploy-production
```

Expected: PASS，失败路径没有调用部署切换。

- [ ] **Step 5: 提交**

```bash
git add scripts/deploy_production.py scripts/deploy-production \
  tests/test_production_orchestration.py
git commit -m "feat: add one-command production deployment"
```

### Task 8: 接入质量门禁并更新操作文档

**Files:**
- Modify: `scripts/check.sh`
- Modify: `tests/test_release_entrypoints.py`
- Modify: `README.md`

- [ ] **Step 1: 写入入口文档契约测试**

在 `tests/test_release_entrypoints.py` 增加：

```python
def test_readme_documents_native_server_prod_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "./scripts/provision-production" in readme
    assert "./scripts/deploy-production" in readme
    assert "http://10.8.0.45:9120" in readme
    assert "http://192.168.100.163:9120" in readme
    assert "Docker" in readme and "不使用" in readme
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --frozen pytest tests/test_release_entrypoints.py \
  -k native_server_prod -q
```

Expected: FAIL，README 尚未记录新入口。

- [ ] **Step 3: 更新文档与检查入口**

README 将旧 Mac 的长命令标记为历史兼容流程，新增：一次性初始化、日常部署、
预期摘要、失败语义、双地址、非 Docker、空数据库和旧环境退役说明。

`scripts/check.sh` 增加新 Python 测试文件、两个 shell `sh -n` 检查和秘密扫描：

```text
KI_API_TOKEN=实际值
AI_API_KEY=实际值
VOLC_API_KEY=实际值
TOS_SK=实际值
```

扫描只匹配赋值内容，不把允许出现的变量名称误报为秘密。

- [ ] **Step 4: 运行发布入口与结构检查**

Run:

```bash
uv run --frozen pytest tests/test_release_entrypoints.py -q
uv run --frozen python scripts/check_structure_baseline.py
git diff --check
```

Expected: PASS，无结构基线增长和空白错误。

- [ ] **Step 5: 提交**

```bash
git add README.md scripts/check.sh tests/test_release_entrypoints.py
git commit -m "docs: document native production deployment"
```

### Task 9: 完整本地验证与代码审查

**Files:**
- Verify only

- [ ] **Step 1: 运行后端与部署专项测试**

Run:

```bash
uv run --frozen pytest \
  tests/test_backend_deploy.py \
  tests/test_preflight_backend_deploy.py \
  tests/test_build_backend_wheel.py \
  tests/test_systemd_backend_deploy.py \
  tests/test_provision_backend_systemd.py \
  tests/test_production_target.py \
  tests/test_production_orchestration.py \
  tests/test_release_entrypoints.py -q
```

Expected: PASS，零失败。

- [ ] **Step 2: 运行完整质量门禁和正式构建**

Run:

```bash
./scripts/check.sh
```

Expected: PASS，后端、前端、类型检查、结构检查和生产构建全部成功。

- [ ] **Step 3: 执行脱敏与差异检查**

Run:

```bash
git diff --check
git status --short
rg -n '(KI_API_TOKEN|AI_API_KEY|VOLC_API_KEY|TOS_SK)=[^<{$[:space:]]' \
  scripts tests README.md docs/superpowers
```

Expected: `git diff --check` 无输出；秘密扫描无匹配；状态只包含计划内文件。

- [ ] **Step 4: 请求代码审查并修复发现**

使用 `superpowers:requesting-code-review` 对设计覆盖、部署安全、回滚完整性和测试
缺口进行审查。任何修复都先补失败测试，再实现并重跑 Task 9 的全部验证。

- [ ] **Step 5: 提交审查修复**

若有修复，只暂存本计划允许修改的部署文件：

```bash
git add src/zhiji_backend/paths.py src/zhiji_backend/main.py \
  src/zhiji_backend/credential_store.py src/zhiji_backend/cli.py \
  scripts/deploy_backend.py scripts/deploy_backend_systemd.py \
  scripts/production_target.py scripts/provision_backend_systemd.py \
  scripts/provision_production.py scripts/provision-production \
  scripts/deploy_production.py scripts/deploy-production scripts/check.sh \
  tests/test_backend_deploy.py tests/test_systemd_backend_deploy.py \
  tests/test_provision_backend_systemd.py tests/test_production_target.py \
  tests/test_production_orchestration.py tests/test_release_entrypoints.py \
  tests/test_system_config_security.py tests/test_access_security.py README.md
git commit -m "fix: harden native production deployment"
```

若无修复，不创建空提交。

### Task 10: 首次初始化、部署和迁移验收

**Files:**
- Production operation only; do not edit repository files during this task

- [ ] **Step 1: 确认已发布来源**

Run:

```bash
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

Expected: 两个 SHA 完全相同，工作区无制品相关修改。

- [ ] **Step 2: 运行初始化 dry-run**

Run:

```bash
./scripts/provision-production --dry-run
```

Expected: 目标显示为 `server-prod / 10.8.0.45 / server`，只列出知己目录、
systemd、sudoers 和两条 UFW allow，没有其他服务变更。

- [ ] **Step 3: 执行一次性初始化**

Run:

```bash
./scripts/provision-production
```

Expected: Python 3.12.13、FFmpeg、目录、非 root SSH、systemd 单元和 UFW
验证全部 PASS；服务尚未承载旧数据。

- [ ] **Step 4: 验证已安全迁移的配置和新令牌文件**

Run:

```bash
ssh zhiji@10.8.0.45 'stat -c "%U %G %a" /etc/zhiji/zhiji.env; sed -E "s/=.*//" /etc/zhiji/zhiji.env | sort'
stat -f '%Su %Sg %Lp' "$HOME/.config/zhiji/server-prod-token"
```

Expected: 远端文件为 `zhiji zhiji 600`，只显示 `AI_*`、`VOLC_*`、`TOS_*`、
`KI_API_TOKEN` 和 `KI_ALLOWED_HOSTS` 等变量名称；本地 token 文件为当前用户
所有且权限 `600`。输出中没有任何配置值。

- [ ] **Step 5: 首次一键部署**

Run:

```bash
./scripts/deploy-production
```

Expected: 3–5 分钟内输出 PASS 摘要；首次下载依赖较慢时允许延长到 10 分钟。

- [ ] **Step 6: 验证服务、数据库与双网段访问**

Run:

```bash
ssh zhiji@10.8.0.45 'sudo -n /usr/bin/systemctl is-active zhiji.service'
ssh zhiji@10.8.0.45 '/srv/apps/zhiji/current/venv/bin/python -c "import sqlite3; print(sqlite3.connect(\"/data/apps/zhiji/data/intelligence.sqlite\").execute(\"PRAGMA quick_check\").fetchone()[0])"'
curl -fsS http://10.8.0.45:9120/api/health
```

Expected: `active`、`ok` 和健康 JSON；局域网设备另外验证
`http://192.168.100.163:9120`。

- [ ] **Step 7: 完成真实业务验收**

在真实浏览器提交一个抖音分享并验证：处理队列节点实时更新、FFmpeg、火山引擎
转写、内容落库、转写原文默认 tab、标题修改、三个不超过 20 字的 AI 标题和
媒体播放。并行观察 systemd 与错误日志至少 35 秒。

Expected: 全链路成功，无密钥、权限、DNS、FFmpeg 或时区错误。

- [ ] **Step 8: 退役旧正式服务**

仅在 Step 6–7 全部通过后停止并禁用旧 Mac 的 `com.zhiji.backend`，随后验证
`10.8.0.105:9120` 不再监听，`10.8.0.45:9120` 持续健康。

旧数据删除不属于本步骤。若用户仍要求删除，必须另行列出精确路径、备份状态
和不可恢复影响并取得最终确认。
