# Douyin DoH Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让抖音媒体下载在 Fake-IP 代理环境中通过固定 Google DoH 获取真实公网 IP，同时保留现有逐跳 SSRF、固定 IP、TLS/SNI/Host 校验，并将北京时间修复随 `2.0.0+108` 部署。

**Architecture:** 新增抖音专用 `douyin_dns` 解析器：先调用系统 DNS，只有全部结果都在 `198.18.0.0/15` 时才分别查询固定 DoH 的 A 和 AAAA 记录，且只返回格式有效的公网地址。`douyin` 门面只替换默认 resolver 并移除旧域名白名单；通用 `remote_transport` 不改行为，继续负责逐跳 URL 校验、固定 IP 连接和 TLS 主机名。

**Tech Stack:** Python 3.12、requests、ipaddress、pytest、Ruff、React 19、TypeScript 6、Vite 8、原子 wheel 部署脚本

---

## File Map

- Create `src/zhiji_backend/ingest/douyin_dns.py`: 抖音专用系统 DNS 分类、固定 Google DoH 查询和公网结果校验。
- Create `tests/test_ingest_douyin_dns.py`: 覆盖 DoH 触发边界、A/AAAA、失败关闭和请求隔离。
- Modify `src/zhiji_backend/ingest/douyin.py`: 默认使用抖音解析器，删除 Fake-IP 域名放行逻辑。
- Modify `tests/test_ingest_remote_transport.py`: 删除旧白名单测试，改为动态 CDN 三跳与通用传输拒绝 Fake-IP 的集成回归。
- Verify `app/frontend/src/pages/GlobalDockQueueOverlay.tsx`: 已有 `formatTimeBeijing` 修复随同制品构建，不再修改。

### Task 1: Define the Fake-IP fallback contract with failing tests

**Files:**
- Create: `tests/test_ingest_douyin_dns.py`
- Create later: `src/zhiji_backend/ingest/douyin_dns.py`

- [ ] **Step 1: Write tests for normal system answers and the exact fallback gate**

Create a small response double and tests using the intended public API:

```python
from unittest.mock import MagicMock

import pytest
import requests

from zhiji_backend.ingest.douyin_dns import DOH_ENDPOINT, resolve_douyin_host


class DoHResponse:
    def __init__(self, payload: dict, *, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


def test_public_system_answer_bypasses_doh():
    doh_get = MagicMock(side_effect=AssertionError("DoH must not run"))
    result = resolve_douyin_host(
        "cdn.example",
        443,
        system_resolver=lambda _host, _port: ["127.0.0.1", "93.184.216.34"],
        doh_get=doh_get,
    )
    assert result == ["127.0.0.1", "93.184.216.34"]
    doh_get.assert_not_called()


@pytest.mark.parametrize(
    "answers",
    [
        ["127.0.0.1"],
        ["10.0.0.2"],
        ["169.254.1.2"],
        ["::1"],
        ["fd00::1"],
        ["fe80::1"],
        ["198.18.0.1", "10.0.0.2"],
    ],
)
def test_non_fake_private_answers_do_not_trigger_doh(answers):
    doh_get = MagicMock(side_effect=AssertionError("DoH must not run"))
    assert resolve_douyin_host(
        "internal.example",
        443,
        system_resolver=lambda _host, _port: answers,
        doh_get=doh_get,
    ) == answers
    doh_get.assert_not_called()
```

- [ ] **Step 2: Write the A and AAAA Fake-IP fallback test**

```python
def test_all_fake_ip_answers_query_fixed_doh_for_a_and_aaaa():
    responses = {
        "A": DoHResponse({"Status": 0, "Answer": [
            {"type": 1, "data": "93.184.216.34"},
            {"type": 5, "data": "ignored.example."},
        ]}),
        "AAAA": DoHResponse({"Status": 0, "Answer": [
            {"type": 28, "data": "2606:2800:220:1:248:1893:25c8:1946"},
        ]}),
    }
    calls = []

    def doh_get(url, **kwargs):
        calls.append((url, kwargs))
        return responses[kwargs["params"]["type"]]

    result = resolve_douyin_host(
        "dynamic.cdn.example",
        443,
        system_resolver=lambda _host, _port: ["198.18.40.216"],
        doh_get=doh_get,
    )

    assert result == [
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    ]
    assert [call[0] for call in calls] == [DOH_ENDPOINT, DOH_ENDPOINT]
    assert [call[1]["params"] for call in calls] == [
        {"name": "dynamic.cdn.example", "type": "A"},
        {"name": "dynamic.cdn.example", "type": "AAAA"},
    ]
    assert all(call[1]["allow_redirects"] is False for call in calls)
    assert all(call[1]["headers"] == {"Accept": "application/dns-json"} for call in calls)
```

- [ ] **Step 3: Run the focused test file and verify RED**

Run:

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_douyin_dns.py
```

Expected: collection fails with `ModuleNotFoundError` for `zhiji_backend.ingest.douyin_dns`; this proves the new behavior does not exist yet.

- [ ] **Step 4: Commit only the failing contract tests**

```bash
git add tests/test_ingest_douyin_dns.py
git commit -m "test: define Douyin DoH resolver contract"
```

### Task 2: Implement the minimal fail-closed resolver

**Files:**
- Create: `src/zhiji_backend/ingest/douyin_dns.py`
- Test: `tests/test_ingest_douyin_dns.py`

- [ ] **Step 1: Implement the exact system classification and fixed DoH request**

Create the module with this interface and behavior:

```python
from __future__ import annotations

import ipaddress
from collections.abc import Callable

import requests  # type: ignore

from .remote_transport import _resolve_host

DOH_ENDPOINT = "https://dns.google/resolve"
DOH_TIMEOUT = (5, 10)
_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
_QUERY_TYPES = (("A", 1), ("AAAA", 28))


def _is_all_fake_ip(addresses: list[str]) -> bool:
    if not addresses:
        return False
    try:
        parsed = [ipaddress.ip_address(value) for value in addresses]
    except ValueError:
        return False
    return all(
        address.version == 4 and address in _FAKE_IP_NETWORK
        for address in parsed
    )


def _has_global_ip(addresses: list[str]) -> bool:
    try:
        return any(ipaddress.ip_address(value).is_global for value in addresses)
    except ValueError:
        return False


def _query_doh(host: str, *, doh_get: Callable = requests.get) -> list[str]:
    addresses: set[str] = set()
    try:
        for query_name, answer_type in _QUERY_TYPES:
            response = doh_get(
                DOH_ENDPOINT,
                params={"name": host, "type": query_name},
                headers={"Accept": "application/dns-json"},
                timeout=DOH_TIMEOUT,
                allow_redirects=False,
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("unexpected DoH status")
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("Status") != 0:
                raise ValueError("unsuccessful DoH response")
            for answer in payload.get("Answer") or []:
                if not isinstance(answer, dict) or answer.get("type") != answer_type:
                    continue
                address = ipaddress.ip_address(answer.get("data", ""))
                if address.is_global:
                    addresses.add(str(address))
    except (requests.RequestException, TypeError, ValueError) as exc:
        raise ValueError("抖音媒体公网 DNS 解析失败") from exc
    if not addresses:
        raise ValueError("抖音媒体公网 DNS 未返回可用地址")
    return sorted(
        addresses,
        key=lambda value: (
            ipaddress.ip_address(value).version,
            int(ipaddress.ip_address(value)),
        ),
    )


def resolve_douyin_host(
    host: str,
    port: int,
    *,
    system_resolver: Callable[[str, int], list[str]] = _resolve_host,
    doh_get: Callable = requests.get,
) -> list[str]:
    addresses = system_resolver(host, port)
    if _has_global_ip(addresses) or not _is_all_fake_ip(addresses):
        return addresses
    return _query_doh(host, doh_get=doh_get)
```

Keep the endpoint constant and do not accept endpoint, Session, Cookie, media headers, or cache arguments.

- [ ] **Step 2: Run the focused tests and verify GREEN**

Run:

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_douyin_dns.py
```

Expected: all current resolver tests pass.

- [ ] **Step 3: Add fail-closed response cases one behavior at a time**

Add parameterized tests proving each case raises only a stable `ValueError` and never returns a connection candidate:

```python
@pytest.mark.parametrize(
    "payload",
    [
        {"Status": 2, "Answer": [{"type": 1, "data": "93.184.216.34"}]},
        {"Status": 0, "Answer": []},
        {"Status": 0, "Answer": [{"type": 1, "data": "not-an-ip"}]},
        {"Status": 0, "Answer": [{"type": 1, "data": "127.0.0.1"}]},
        {"Status": 0, "Answer": [{"type": 1, "data": "10.0.0.2"}]},
    ],
)
def test_doh_invalid_or_non_public_answers_fail_closed(payload):
    with pytest.raises(ValueError, match="抖音媒体公网 DNS"):
        resolve_douyin_host(
            "cdn.example",
            443,
            system_resolver=lambda _host, _port: ["198.18.0.1"],
            doh_get=lambda *_args, **_kwargs: DoHResponse(payload),
        )


@pytest.mark.parametrize("error", [requests.Timeout("timeout"), requests.ConnectionError("down")])
def test_doh_network_errors_fail_closed(error):
    with pytest.raises(ValueError, match="抖音媒体公网 DNS"):
        resolve_douyin_host(
            "cdn.example",
            443,
            system_resolver=lambda _host, _port: ["198.18.0.1"],
            doh_get=MagicMock(side_effect=error),
        )
```

Because both A and AAAA must be queried, use per-query response fixtures so an empty family may coexist with a valid other family; a transport error or non-zero DNS status in either query still fails the whole resolution.

- [ ] **Step 4: Run each new case before and after the minimal implementation adjustment**

Run each newly added node with `-q`; before adjusting code, confirm the expected failure, then change only `_query_doh` and rerun until it passes. Finally run:

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_douyin_dns.py
```

Expected: all resolver tests pass with no warning or leaked payload/URL in exception messages.

- [ ] **Step 5: Run Ruff and commit the resolver**

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python -m ruff check \
  src/zhiji_backend/ingest/douyin_dns.py tests/test_ingest_douyin_dns.py
git add src/zhiji_backend/ingest/douyin_dns.py tests/test_ingest_douyin_dns.py
git commit -m "feat: resolve Douyin fake IPs through fixed DoH"
```

Expected: Ruff exits zero, then the commit succeeds.

### Task 3: Wire the resolver into every Douyin redirect hop

**Files:**
- Modify: `src/zhiji_backend/ingest/douyin.py:1-358`
- Modify: `tests/test_ingest_remote_transport.py:13-212`
- Test: `tests/test_ingest_douyin_dns.py`

- [ ] **Step 1: Replace old allowlist tests with failing facade security tests**

Delete tests that expect `aweme.snssdk.com` or `*.365yg.com` Fake-IP connections. First add tests that must fail against the current facade:

```python
def test_douyin_resolver_delegates_to_douyin_dns(monkeypatch):
    resolver = MagicMock(return_value=["93.184.216.34"])
    monkeypatch.setattr(douyin_dns, "resolve_douyin_host", resolver)

    assert douyin._resolve_host("dynamic.example", 443) == ["93.184.216.34"]
    resolver.assert_called_once_with("dynamic.example", 443)


def test_douyin_facade_no_longer_allows_fake_ip_connections():
    with pytest.raises(ValueError, match="公网"):
        douyin._validate_remote_url(
            "https://aweme.snssdk.com/video.mp4",
            resolver=lambda _host, _port: ["198.18.0.190"],
        )
```

Then add a three-hop test to preserve the existing transport guarantee that the supplied resolver runs independently on every dynamic redirect hop:

```python
def test_douyin_safe_get_resolves_every_dynamic_redirect_hop():
    responses = [
        Response(status_code=302, headers={"Location": "https://v5.cdn.example/two"}),
        Response(status_code=302, headers={"Location": "https://dynamic.example/final"}),
        Response(),
    ]
    resolved_hosts = []
    connections = []

    def resolver(host, _port):
        resolved_hosts.append(host)
        return {
            "aweme.snssdk.com": ["93.184.216.10"],
            "v5.cdn.example": ["93.184.216.11"],
            "dynamic.example": ["93.184.216.12"],
        }[host]

    def connection_factory(scheme, ip, port, hostname):
        connections.append((scheme, ip, port, hostname))
        return Connection(responses, [])

    result = douyin._safe_get(
        None,
        "https://aweme.snssdk.com/one",
        headers={"User-Agent": "test"},
        timeout=(1, 2),
        resolver=resolver,
        max_redirects=2,
        connection_factory=connection_factory,
    )

    assert resolved_hosts == [
        "aweme.snssdk.com", "v5.cdn.example", "dynamic.example"
    ]
    assert connections == [
        ("https", "93.184.216.10", 443, "aweme.snssdk.com"),
        ("https", "93.184.216.11", 443, "v5.cdn.example"),
        ("https", "93.184.216.12", 443, "dynamic.example"),
    ]
    result.close()
```

Import `douyin_dns` in the test module. Keep the existing facade-default assertion that the public signature exposes `douyin._resolve_host`; the delegation test now defines what that wrapper does.

- [ ] **Step 2: Run the focused integration tests and verify RED**

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_remote_transport.py tests/test_ingest_douyin_dns.py
```

Expected: `test_douyin_resolver_delegates_to_douyin_dns` fails because the facade still calls the raw system resolver, and `test_douyin_facade_no_longer_allows_fake_ip_connections` fails because the old allow hook still accepts the address. The three-hop transport test already passes and guards unchanged behavior.

- [ ] **Step 3: Make the minimal facade change**

In `douyin.py`:

```python
from . import douyin_dns, douyin_download, remote_transport


def _resolve_host(host: str, port: int) -> list[str]:
    return douyin_dns.resolve_douyin_host(host, port)


def _validate_remote_url(
    url: str,
    *,
    resolver: Callable[[str, int], list[str]],
) -> _RemoteTarget:
    return remote_transport._validate_remote_url(url, resolver=resolver)
```

Remove the `ipaddress` import, `_PROXY_FAKE_IP_NETWORK`, and `_allow_trusted_douyin_fake_ip`. Preserve `_download_video_signature`, `_OMITTED`, call-time monkeypatch compatibility, injected custom resolvers, redirect limits, Cookie filtering, and connection factory behavior.

- [ ] **Step 4: Verify focused GREEN and the security regression**

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_remote_transport.py tests/test_ingest_douyin_dns.py
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_remote_transport.py::test_validate_remote_url_rejects_benchmark_fake_ip_by_default
```

Expected: both commands pass; no path in the Douyin facade can connect directly to `198.18.0.0/15`.

- [ ] **Step 5: Run Ruff and commit the integration**

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python -m ruff check \
  src/zhiji_backend/ingest/douyin.py \
  src/zhiji_backend/ingest/douyin_dns.py \
  tests/test_ingest_douyin_dns.py tests/test_ingest_remote_transport.py
git add src/zhiji_backend/ingest/douyin.py src/zhiji_backend/ingest/douyin_dns.py \
  tests/test_ingest_douyin_dns.py tests/test_ingest_remote_transport.py
git commit -m "fix: use DoH for Douyin fake IP redirects"
```

### Task 4: Run full regression and build verification

**Files:**
- Verify: all backend and frontend sources
- Generate: `app/frontend/dist/`

- [ ] **Step 1: Run the complete backend suite with the isolated worktree first on `PYTHONPATH`**

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q
```

Expected: at least the prior 1636-test baseline plus the new resolver tests pass, with zero failures.

- [ ] **Step 2: Run complete Python lint**

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python -m ruff check .
```

Expected: zero lint errors.

- [ ] **Step 3: Run frontend tests, typecheck, and production build under Node 22.17.0**

```bash
cd app/frontend
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:cinematic-scene
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:cinematic-ingest
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:media-transport
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:quality-gates
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run typecheck
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run build
```

Expected: the prior 302-test frontend baseline passes, TypeScript exits zero, and Vite creates production assets. Confirm the queue source still calls `formatTimeBeijing(item.created_at)`.

- [ ] **Step 4: Inspect the final diff and commit only required source/test changes**

```bash
git diff --check
git status --short
git diff origin/main -- src/zhiji_backend/ingest/douyin.py \
  src/zhiji_backend/ingest/douyin_dns.py tests/test_ingest_douyin_dns.py \
  tests/test_ingest_remote_transport.py app/frontend/src/pages/GlobalDockQueueOverlay.tsx
```

Expected: no whitespace errors, no generated frontend files staged, no unrelated edits, and the diff contains both the approved DoH behavior and existing Beijing-time display fix.

### Task 5: Build SHA-specific `2.0.0+108` artifacts

**Files:**
- Generate: `dist/backend-${SOURCE_SHA}/`
- Preserve: all remote `/Users/mrh/Documents/KI/packages/*` stages

- [ ] **Step 1: Run read-only production preflight**

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" \
  --legacy-name 2.0.0+107 \
  --target-name 2.0.0+108 \
  --expect-legacy present --expect-current present \
  --expect-target absent --expect-stage absent \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
```

Expected JSON: token, allowed hosts, health, database and disk checks are `ok`; `2.0.0+107` and current are present; `2.0.0+108` and the SHA stage are absent. Stop if any condition differs.

- [ ] **Step 2: Build the wheel and locked runtime requirements**

```bash
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH \
NPM_CONFIG_CACHE=/private/tmp/zhiji-npm-cache-douyin-doh \
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/build_backend_wheel.py \
  --outdir "dist/backend-${SOURCE_SHA}"

uv export --frozen --no-dev --no-emit-project --no-editable \
  --format requirements.txt \
  --output-file "dist/backend-${SOURCE_SHA}/requirements.lock"
```

Expected: one `zhiji_backend-2.0.0-py3-none-any.whl` is produced. Inspect it with `unzip -l` and require both `zhiji_backend/ingest/douyin_dns.py` and `zhiji_backend/frontend_dist/assets/`; inspect the bundled frontend JavaScript for the Beijing formatter marker.

- [ ] **Step 3: Assemble and verify bootstrap checksums**

```bash
cp scripts/deploy_backend.py scripts/bootstrap_legacy_runtime.py \
  scripts/preflight_backend_deploy.py scripts/provision_remote_access.py \
  scripts/build_remote_wheelhouse.py scripts/backend-build-requirements.lock \
  "dist/backend-${SOURCE_SHA}/"
cd "dist/backend-${SOURCE_SHA}"
shasum -a 256 zhiji_backend-2.0.0-py3-none-any.whl requirements.lock \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py build_remote_wheelhouse.py \
  backend-build-requirements.lock > BOOTSTRAP_SHA256SUMS
shasum -a 256 -c BOOTSTRAP_SHA256SUMS
```

Expected: every bootstrap file reports `OK`.

- [ ] **Step 4: Upload to an immutable SHA stage and build x86_64 wheelhouse**

```bash
ssh zhiji-prod "mkdir -m 700 /Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
scp zhiji_backend-2.0.0-py3-none-any.whl BOOTSTRAP_SHA256SUMS \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py requirements.lock build_remote_wheelhouse.py \
  backend-build-requirements.lock \
  "zhiji-prod:/Users/mrh/Documents/KI/packages/${SOURCE_SHA}/"
ssh zhiji-prod "cd /Users/mrh/Documents/KI/packages/${SOURCE_SHA} && shasum -a 256 -c BOOTSTRAP_SHA256SUMS"
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/build_remote_wheelhouse.py \
  --stage /Users/mrh/Documents/KI/packages/${SOURCE_SHA} \
  --expected-machine x86_64"
ssh zhiji-prod "cd /Users/mrh/Documents/KI/packages/${SOURCE_SHA} && shasum -a 256 -c SHA256SUMS"
```

Expected: upload checks and final complete manifest report `OK`; no prior stage is removed or overwritten.

### Task 6: Deploy, retry the original task, and observe production

**Files:**
- Preserve: `/Users/mrh/Documents/KI/data/**`
- Preserve: `/Users/mrh/Documents/KI/runtime/versions/2.0.0+102` through `2.0.0+107`
- Preserve: `/Users/mrh/Documents/KI/backups/deploy-*.sqlite`
- Deploy: `/Users/mrh/Documents/KI/runtime/versions/2.0.0+108`

- [ ] **Step 1: Capture pre-deploy inventories and database integrity**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' \
  > /private/tmp/zhiji-versions-before-108.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' \
  > /private/tmp/zhiji-backups-before-108.txt
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"'
```

Expected: `quick_check` is `ok`, foreign-key check emits no rows, and inventory files include `2.0.0+107` plus `deploy-20260803-103032.sqlite`.

- [ ] **Step 2: Atomically deploy with history preservation**

```bash
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/deploy_backend.py v2.0.0+108 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/zhiji_backend-2.0.0-py3-none-any.whl \
  --checksums /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/SHA256SUMS \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --bind-host 0.0.0.0 \
  --health-origin http://127.0.0.1:9120 \
  --preserve-history"
```

Expected: exit zero and `runtime/current` resolves to `2.0.0+108`. If deployment fails or health does not recover, point `runtime/current` back to `runtime/versions/2.0.0+107`, kickstart `gui/$(id -u)/com.zhiji.backend`, verify `/api/health`, and stop.

- [ ] **Step 3: Prove service health, history preservation, and database integrity**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' \
  > /private/tmp/zhiji-versions-after-108.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' \
  > /private/tmp/zhiji-backups-after-108.txt
comm -23 /private/tmp/zhiji-versions-before-108.txt /private/tmp/zhiji-versions-after-108.txt
comm -23 /private/tmp/zhiji-backups-before-108.txt /private/tmp/zhiji-backups-after-108.txt
ssh zhiji-prod 'readlink /Users/mrh/Documents/KI/runtime/current'
ssh zhiji-prod 'curl -fsS http://127.0.0.1:9120/api/health'
ssh zhiji-prod 'launchctl print gui/501/com.zhiji.backend'
ssh zhiji-prod 'lsof -nP -iTCP:9120 -sTCP:LISTEN'
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"'
```

Expected: both `comm` commands emit nothing; all earlier versions and backups remain; current is `2.0.0+108`; health is `{"ok":true}`; launchd is running on `*:9120`; database checks remain clean.

- [ ] **Step 4: Run the post-deploy preflight**

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" \
  --legacy-name 2.0.0+107 \
  --target-name 2.0.0+108 \
  --expect-legacy present --expect-current present \
  --expect-target present --expect-stage present \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
```

Expected: authenticated system health is 200 with version `2.0.0`, target and stage are present, and every safety check is `ok`.

- [ ] **Step 5: Retry the existing failed task through the authenticated API**

Use the already authenticated in-app browser to call the existing UI retry action for `task-d7ff5704ef2c`, or run a server-local Python request that reads `KI_API_TOKEN` from `/Users/mrh/Documents/KI/.env` internally and sends:

```text
POST http://127.0.0.1:9120/api/ingest/queue/task-d7ff5704ef2c/retry
Authorization: Bearer <value read locally from .env>
```

Do not print the token and do not update SQLite directly. Poll authenticated `GET /api/ingest/queue?limit=30` every few seconds and record only task status, stage, retry count, and redacted error category.

Expected: the original task changes from `error` through active processing to `done`; it does not fail at the media DNS/download stage. If a downstream external service is temporarily unavailable, record the new stage and error separately rather than claiming the download fix failed.

- [ ] **Step 6: Verify the queue UI and Beijing time in the real browser**

Open the production queue in an authenticated browser at desktop `1440x900` and mobile `390x844`. Confirm the known UTC value `2026-08-03 09:56:03` renders as `2026/8/3 17:56:03` on desktop, and that mobile follows the existing responsive rule without overlap or horizontal overflow.

Expected: Beijing time is correct, queue status is current, controls remain usable, and there are no console errors.

- [ ] **Step 7: Observe for at least 30 seconds and apply rollback criteria**

Capture launchd PID/restart count and stderr tail, wait at least 30 seconds, then capture them again with health and queue status. Roll back to `2.0.0+107` only if the service crashes/restarts, health fails, database integrity changes, or the new resolver causes a reproducible regression; preserve the `2.0.0+108` artifacts and backup for diagnosis.

Expected: PID remains stable, health stays 200, no new traceback or repeated restart appears, and the task remains `done`.

- [ ] **Step 8: Record final evidence**

```bash
git status --short
git log -5 --oneline
```

Record the deployed source SHA, wheel SHA256, remote runtime target, new backup filename, retained history counts, test totals, final task state, Beijing-time browser evidence, and observation timestamps. Do not claim completion unless every item has fresh command or browser evidence.
