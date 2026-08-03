# 抖音 Fake-IP 下载与队列北京时间修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不放宽通用 SSRF 防护的前提下兼容抖音 HTTPS CDN 的代理 Fake-IP，并让处理队列按北京时间显示 UTC 时间。

**Architecture:** 通用远程传输验证器增加一个默认关闭的非公网地址策略钩子；抖音 facade 仅为受信任 HTTPS 媒体主机和 `198.18.0.0/15` 提供该策略。前端复用现有 `formatTimeBeijing`，不改变数据库与 API 的 UTC 契约。

**Tech Stack:** Python 3.12、pytest、React 19、TypeScript、Node test runner、Vite、SQLite。

---

### Task 1: 建立干净基线

**Files:**
- Verify: `tests/test_ingest_remote_transport.py`
- Verify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: 安装或复用隔离工作区依赖**

后端使用项目现有 Python 3.12 虚拟环境运行；前端在隔离工作区执行 `npm ci`，不修改锁文件。

- [ ] **Step 2: 运行后端基线**

Run: `/Users/yuk/Documents/zhiji/ki/.venv/bin/pytest -q`
Expected: 全部通过。

- [ ] **Step 3: 运行前端相关基线**

Run: `npm run test:cinematic-scene`
Expected: 全部通过。

### Task 2: 为受限 Fake-IP 策略编写失败测试

**Files:**
- Modify: `tests/test_ingest_remote_transport.py`

- [ ] **Step 1: 写通用传输层拒绝测试**

增加测试，直接调用 `remote_transport._validate_remote_url`，断言默认策略仍拒绝解析到 `198.18.0.190` 的任意 URL。

- [ ] **Step 2: 写抖音受信任主机允许测试**

增加参数化测试，断言 `douyin._validate_remote_url` 接受：

```python
"https://aweme.snssdk.com/video.mp4"
"https://video.365yg.com/video.mp4"
```

两者的 resolver 均返回 `198.18.0.190`，并断言返回的 `public_ips` 为该地址。

- [ ] **Step 3: 写安全边界测试**

增加参数化测试，断言以下组合仍抛出包含“公网”的 `ValueError`：

```python
("https://evil.example/video.mp4", "198.18.0.190")
("http://aweme.snssdk.com/video.mp4", "198.18.0.190")
("https://aweme.snssdk.com/video.mp4", "192.168.1.20")
```

- [ ] **Step 4: 运行测试确认红灯**

Run: `/Users/yuk/Documents/zhiji/ki/.venv/bin/pytest tests/test_ingest_remote_transport.py -q`
Expected: 新增的受信任主机允许测试失败，原因是当前实现拒绝 `198.18.0.190`。

### Task 3: 实现最小 Fake-IP 兼容

**Files:**
- Modify: `src/zhiji_backend/ingest/remote_transport.py`
- Modify: `src/zhiji_backend/ingest/douyin.py`
- Test: `tests/test_ingest_remote_transport.py`

- [ ] **Step 1: 给通用验证器增加默认关闭策略**

在 `_validate_remote_url` 增加关键字参数：

```python
allow_non_global_address: Callable[[str, str, ipaddress._BaseAddress], bool] | None = None
```

优先保留所有 `is_global` 地址；仅当没有公网地址时，才筛选策略明确允许的地址。策略不存在或没有匹配时继续抛出原有错误。

- [ ] **Step 2: 增加抖音专用策略**

在 `douyin.py` 定义 `198.18.0.0/15` 网络和策略函数。策略同时校验 HTTPS、主机为 `aweme.snssdk.com` 或 `365yg.com` 及其子域名、地址属于该网段。

- [ ] **Step 3: 仅从抖音 facade 注入策略**

`douyin._validate_remote_url` 调用通用验证器时传入该策略；其他调用方保持默认行为。

- [ ] **Step 4: 运行测试确认绿灯**

Run: `/Users/yuk/Documents/zhiji/ki/.venv/bin/pytest tests/test_ingest_remote_transport.py tests/test_ingest_douyin.py -q`
Expected: 全部通过。

- [ ] **Step 5: 提交后端修复**

```bash
git add src/zhiji_backend/ingest/remote_transport.py src/zhiji_backend/ingest/douyin.py tests/test_ingest_remote_transport.py
git commit -m "fix: allow trusted Douyin proxy fake IPs"
```

### Task 4: 为队列北京时间编写失败测试并实现

**Files:**
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`
- Modify: `app/frontend/src/pages/GlobalDockQueueOverlay.tsx`

- [ ] **Step 1: 写失败组合测试**

断言队列浮层导入 `formatTimeBeijing`，使用 `formatTimeBeijing(item.created_at)`，并且不再出现 `item.created_at?.slice(0, 19)`。

- [ ] **Step 2: 运行测试确认红灯**

Run: `node --experimental-strip-types --test src/components/react-bits/dualNavigationComposition.test.mjs`
Expected: 因尚未导入和调用 `formatTimeBeijing` 而失败。

- [ ] **Step 3: 实现最小展示修复**

在 `GlobalDockQueueOverlay.tsx` 导入现有工具，并替换为：

```tsx
<em>{formatTimeBeijing(item.created_at) || '--'}</em>
```

- [ ] **Step 4: 运行测试确认绿灯**

Run: `node --experimental-strip-types --test src/components/react-bits/dualNavigationComposition.test.mjs`
Expected: 全部通过。

- [ ] **Step 5: 提交前端修复**

```bash
git add app/frontend/src/pages/GlobalDockQueueOverlay.tsx app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs
git commit -m "fix: display ingest queue times in Beijing time"
```

### Task 5: 全量验证与构建

**Files:**
- Verify: `src/zhiji_backend/ingest/remote_transport.py`
- Verify: `src/zhiji_backend/ingest/douyin.py`
- Verify: `app/frontend/src/pages/GlobalDockQueueOverlay.tsx`

- [ ] **Step 1: 运行后端全量测试与静态检查**

Run: `/Users/yuk/Documents/zhiji/ki/.venv/bin/pytest -q`
Expected: 全部通过。

Run: `/Users/yuk/Documents/zhiji/ki/.venv/bin/ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 2: 运行前端测试、类型检查和构建**

Run: `npm run test:cinematic-scene`
Expected: 全部通过。

Run: `npm run typecheck`
Expected: exit 0。

Run: `npm run build`
Expected: exit 0，生成生产静态资源。

- [ ] **Step 3: 在生产机做无数据写入的真实下载探针**

使用当前失败任务的原始分享文本调用新 wheel 中的 `parse_share_text` 与受限 `_safe_get`，只读取首个 Range 分片并立即关闭。断言 TLS 校验成功且响应为 `200` 或 `206`。

### Task 6: 安全部署与生产验证

**Files:**
- Build: `dist/zhiji_backend-2.0.0-py3-none-any.whl`
- Preserve: `/Users/mrh/Documents/KI/data/intelligence.sqlite`

- [ ] **Step 1: 记录并备份生产状态**

记录 `runtime/current`、服务 PID、健康接口和数据库 `PRAGMA quick_check`；使用 SQLite backup API 创建带时间戳备份，不复制或删除共享数据目录。

- [ ] **Step 2: 构建并校验 wheel**

Run: `/Users/yuk/Documents/zhiji/ki/.venv/bin/python -m build --wheel`
Expected: wheel 构建成功；记录本地和远端 SHA256 并确保一致。

- [ ] **Step 3: 安装为新不可变版本并切换**

创建下一个 `2.0.0+NNN` 版本目录，安装 wheel，原子切换 `runtime/current`，重启 `com.zhiji.backend`。保留原版本目录和 current 指向用于回滚。

- [ ] **Step 4: 验证服务与数据库**

验证 launchd 为 running、认证健康接口成功、版本正确、`PRAGMA quick_check=ok`，且日志没有新的启动异常。

- [ ] **Step 5: 重试原失败任务并观察**

通过已有认证 API 调用该任务的重试接口，不直接更新数据库。轮询队列状态，确认任务越过下载阶段并最终完成；检查视频、转写和事件详情可访问。

- [ ] **Step 6: 浏览器验证北京时间**

在生产页面打开处理队列，确认该任务显示北京时间而非 UTC，且桌面和窄屏布局无文本重叠。

- [ ] **Step 7: 失败时回滚**

若服务、数据库或任务验证失败，立即把 `runtime/current` 切回原版本并重启；保留失败任务和日志用于后续分析，不删除用户数据。
