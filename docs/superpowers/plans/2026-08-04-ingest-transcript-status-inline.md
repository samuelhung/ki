# 内容详情转写状态同行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将内容采集详情的转写状态移入“创建时间 · 分类”元信息行，同时保持转写按钮和独立事件详情布局不变。

**Architecture:** 先把 `TranscriptActions` 拆成可独立复用的按钮和状态组件，并由原组合组件继续服务独立事件详情。内容采集页分别向详情面板传递按钮和状态节点，详情面板负责把按钮放入标题行、把状态放入元信息行；CSS 只控制该元信息行的单行与局部滚动边界。

**Tech Stack:** React 19、TypeScript 6、Vite 8、CSS、Node.js 内置测试运行器、浏览器 DOM 几何验证

---

## 文件结构

- 修改 `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`：导出独立按钮与状态组件，并保留组合组件。
- 修改 `app/frontend/src/pages/Ingest.tsx`：创建并传递独立按钮和状态节点。
- 修改 `app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx`：分别转发按钮和状态节点。
- 修改 `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx`：按钮留在标题行，状态进入内容元信息行。
- 修改 `app/frontend/src/pages/DualNavigationDemo.css`：定义元信息单行、局部滚动和错误省略规则。
- 修改 `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`：锁定共享组件拆分与独立事件详情兼容。
- 修改 `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`：锁定内容采集的双节点传递和 DOM 顺序。
- 修改 `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`：锁定元信息行响应式 CSS 契约。

### Task 1: 拆分转写按钮与状态组件

**Files:**
- Test: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`
- Modify: `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`

- [ ] **Step 1: 写入失败的组件契约测试**

在 `transcript correction UI opens one workspace from the title row` 测试中加入：

```js
  assert.match(actions, /export function TranscriptActionButton/);
  assert.match(actions, /export function TranscriptStatus/);
  assert.match(
    actions,
    /export function TranscriptActions[\s\S]*<TranscriptActionButton[\s\S]*<TranscriptStatus/,
  );
  for (const copy of ['原始转写', '已人工校验', '已完成语义分段', '已恢复历史版本', '加载转写版本…']) {
    assert.match(actions, new RegExp(copy));
  }
```

- [ ] **Step 2: 运行测试并确认红灯**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/cinematic-ingest/eventDetailComposition.test.mjs
```

Expected: FAIL；失败原因是 `TranscriptActionButton` 和 `TranscriptStatus` 尚未导出，而不是语法或文件读取错误。

- [ ] **Step 3: 实施最小组件拆分**

用以下结构改写 `TranscriptActions.tsx`，保留现有状态文案和组合组件类名：

```tsx
import { FilePenLine, RefreshCw } from 'lucide-react';
import type { TranscriptSnapshot } from '../../pages/EventDetailPage';
import { formatTimeBeijing } from '../../utils';

interface TranscriptActionButtonProps {
  transcript: TranscriptSnapshot | null;
  loading: boolean;
  onOpen: () => void;
}

interface TranscriptStatusProps {
  transcript: TranscriptSnapshot | null;
  loading: boolean;
  error: string;
  refreshRequired: boolean;
  onRefresh: () => void;
}

type TranscriptActionsProps = TranscriptActionButtonProps & TranscriptStatusProps;

function transcriptStatus(transcript: TranscriptSnapshot | null) {
  if (!transcript) return '';
  const time = formatTimeBeijing(transcript.active_revision.created_at);
  if (transcript.active_revision.kind === 'manual') return `已人工校验 · ${time}`;
  if (transcript.active_revision.kind === 'segmented') return `已完成语义分段 · ${time}`;
  if (transcript.active_revision.kind === 'restored') return `已恢复历史版本 · ${time}`;
  return '原始转写';
}

export function TranscriptActionButton({ transcript, loading, onOpen }: TranscriptActionButtonProps) {
  const unavailable = loading || !transcript;
  return <button type="button" onClick={onOpen} disabled={unavailable}
    className="transcript-action-button"
    title="人工修正、AI 语义分段与修订记录">
    <FilePenLine size={14} />转写处理
  </button>;
}

export function TranscriptStatus({
  transcript,
  loading,
  error,
  refreshRequired,
  onRefresh,
}: TranscriptStatusProps) {
  return <div className="transcript-status-inline flex min-w-0 items-center gap-2 text-[10px] text-gray-500">
    {error && <span className="transcript-status-message truncate text-red-400" title={error}>{error}</span>}
    {refreshRequired && <button type="button" onClick={onRefresh}
      className="inline-flex shrink-0 items-center gap-1 text-purple-300 hover:text-purple-200">
      <RefreshCw size={11} />刷新
    </button>}
    {!error && <span>{loading ? '加载转写版本…' : transcriptStatus(transcript)}</span>}
  </div>;
}

export function TranscriptActions(props: TranscriptActionsProps) {
  return <div className="transcript-title-actions ml-auto flex min-w-0 shrink-0 flex-col items-end gap-1.5">
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      <TranscriptActionButton transcript={props.transcript} loading={props.loading} onOpen={props.onOpen} />
    </div>
    <TranscriptStatus
      transcript={props.transcript}
      loading={props.loading}
      error={props.error}
      refreshRequired={props.refreshRequired}
      onRefresh={props.onRefresh}
    />
  </div>;
}
```

- [ ] **Step 4: 运行定向测试并确认绿灯**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/cinematic-ingest/eventDetailComposition.test.mjs
```

Expected: PASS；独立事件详情继续使用 `TranscriptActions`，所有该文件子测试通过。

- [ ] **Step 5: 提交组件拆分**

```bash
git add app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs
git commit -m "refactor: split transcript action and status"
```

### Task 2: 接入内容详情元信息行

**Files:**
- Test: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`
- Test: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: 写入失败的内容详情组合测试**

将 `embedded ingest exposes the transcript revision workflow from the content title row` 中针对单个 `transcriptActions` 的断言替换为：

```js
  assert.match(page, /import \{ TranscriptActionButton, TranscriptStatus \}/);
  assert.match(page, /transcriptActionButton=\{<TranscriptActionButton/);
  assert.match(page, /transcriptStatus=\{<TranscriptStatus/);
  assert.match(workspace, /transcriptActionButton=\{transcriptActionButton\}/);
  assert.match(workspace, /transcriptStatus=\{transcriptStatus\}/);
  assert.match(
    detailPanel,
    /transcript-title-row[\s\S]*<h2[\s\S]*tab === 'body'[\s\S]*transcriptActionButton/,
  );
  assert.match(
    detailPanel,
    /ingest-detail-meta-row[\s\S]*formatTimeBeijing\(item\.created_at\)[\s\S]*item\.topic[\s\S]*tab === 'body'[\s\S]*transcriptStatus/,
  );
  assert.doesNotMatch(detailPanel, /tab === 'body' && transcriptActions/);
```

在 `formal ingest composes a split list orbit and reusable detail workspace` 测试中加入 CSS 契约：

```js
  assert.match(
    shellCss,
    /\.ingest-detail-meta-row\s*\{[^}]*display:\s*flex[^}]*overflow-x:\s*auto[^}]*white-space:\s*nowrap/s,
  );
  assert.match(
    shellCss,
    /\.ingest-detail-meta-row \.transcript-status-message\s*\{[^}]*max-width:[^}]*text-overflow:\s*ellipsis/s,
  );
```

- [ ] **Step 2: 运行两组测试并确认红灯**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test \
  src/components/cinematic-ingest/ingestPageComposition.test.mjs \
  src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: FAIL；失败原因是双节点属性、元信息行和 CSS 契约尚未实现。

- [ ] **Step 3: 在内容采集页创建独立节点**

将 `Ingest.tsx` 的导入改为：

```tsx
import { TranscriptActionButton, TranscriptStatus } from '../components/cinematic-ingest/TranscriptActions';
```

将 `IngestWorkspaceContent` 的转写属性改为：

```tsx
transcriptActionButton={<TranscriptActionButton
  transcript={transcriptWorkflow.transcript}
  loading={transcriptWorkflow.loading}
  onOpen={transcriptWorkflow.openWorkspace}
/>}
transcriptStatus={<TranscriptStatus
  transcript={transcriptWorkflow.transcript}
  loading={transcriptWorkflow.loading}
  error={transcriptWorkflow.error}
  refreshRequired={transcriptWorkflow.refreshRequired}
  onRefresh={transcriptWorkflow.refreshTranscript}
/>}
```

- [ ] **Step 4: 分别转发按钮和状态节点**

在 `IngestWorkspaceContentProps`、参数解构和 `ContentDetailPanel` 调用中，把：

```tsx
transcriptActions: React.ReactNode;
```

替换为：

```tsx
transcriptActionButton: React.ReactNode;
transcriptStatus: React.ReactNode;
```

调用 `ContentDetailPanel` 时传递：

```tsx
transcriptActionButton={transcriptActionButton}
transcriptStatus={transcriptStatus}
```

并在 `useMemo` 依赖数组中用 `transcriptActionButton, transcriptStatus` 替换 `transcriptActions`。

- [ ] **Step 5: 重组内容详情头部**

在 `ContentDetailPanel.tsx` 的属性定义中用：

```tsx
transcriptActionButton?: React.ReactNode;
transcriptStatus?: React.ReactNode;
```

替换 `transcriptActions`，并将头部改为：

```tsx
<header>
  <span>{item ? `${sourceLabel(item.source_id)} · ${statusLabel(item.status)}` : 'CONTENT DETAIL'}</span>
  <div className="transcript-title-row flex flex-wrap items-start justify-between gap-3">
    <h2>{item?.title_cn || item?.title || ingestCopy.detail.titleFallback}</h2>
    {tab === 'body' && transcriptActionButton}
  </div>
  {item && <div className="ingest-detail-meta-row">
    <small>{formatTimeBeijing(item.created_at)} · {item.topic || 'uncategorized'}</small>
    {tab === 'body' && transcriptStatus && <>
      <i className="ingest-detail-meta-separator" aria-hidden="true">·</i>
      {transcriptStatus}
    </>}
  </div>}
</header>
```

- [ ] **Step 6: 添加元信息行 CSS**

在 `DualNavigationDemo.css` 的转写控件样式附近加入：

```css
.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
}

.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-row::-webkit-scrollbar {
  display: none;
}

.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-row small,
.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-separator,
.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-row .transcript-status-inline {
  flex: 0 0 auto;
}

.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-row small {
  display: inline-flex;
}

.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-separator {
  color: rgba(207, 158, 255, .58);
  font-size: 10px;
  font-style: normal;
}

.legacy-ingest-root.is-shell-embedded .ingest-detail-meta-row .transcript-status-message {
  max-width: min(360px, 40vw);
  overflow: hidden;
  text-overflow: ellipsis;
}
```

- [ ] **Step 7: 运行定向测试并确认绿灯**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test \
  src/components/cinematic-ingest/eventDetailComposition.test.mjs \
  src/components/cinematic-ingest/ingestPageComposition.test.mjs \
  src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: PASS；共享组件、内容采集组合、独立事件详情兼容和 CSS 契约全部通过。

- [ ] **Step 8: 检查补丁并提交内容详情改动**

Run:

```bash
git diff --check
git diff -- app/frontend/src/pages/Ingest.tsx app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx app/frontend/src/pages/DualNavigationDemo.css
```

Expected: `git diff --check` 无输出；差异只涉及双节点传递、元信息头部和对应 CSS。

Commit:

```bash
git add \
  app/frontend/src/pages/Ingest.tsx \
  app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx \
  app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx \
  app/frontend/src/pages/DualNavigationDemo.css \
  app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs \
  app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
git commit -m "fix: align transcript status with content metadata"
```

### Task 3: 完整回归与真实状态验证

**Files:**
- Verify: `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`
- Verify: `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx`
- Verify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: 运行完整前端验证**

Run:

```bash
cd app/frontend
npm run test:cinematic-scene
npm run typecheck
npm run build
```

Expected: 全部 Node 子测试通过且无失败；TypeScript 和 Vite 构建退出码为 `0`。

- [ ] **Step 2: 使用现有本地验证服务**

确认 `http://127.0.0.1:5175/#/ingest` 由当前工作树提供；若服务已停止，运行：

```bash
cd app/frontend
npm run dev -- --port 5175
```

Expected: Vite 输出 `Local: http://127.0.0.1:5175/`。如果端口已被其他进程占用，使用下一个可用端口并记录实际 URL。

- [ ] **Step 3: 验证原始转写状态**

选择一条仍使用 `original` 修订的内容，确认可见文本顺序为：

```text
创建时间 · 分类 · 原始转写
```

通过只读 DOM 测量确认内容元信息和转写状态的 `top` 坐标差小于 `1px`，且“转写处理”按钮仍位于标题行右侧。

- [ ] **Step 4: 验证人工校验状态**

选择已人工校验的内容，确认可见文本顺序为：

```text
创建时间 · 分类 · 已人工校验 · 修订时间
```

通过只读 DOM 测量确认 `.ingest-detail-meta-row small` 与 `.transcript-status-inline` 的 `top` 坐标差小于 `1px`，且二者都位于 `.ingest-detail-meta-row` 边界内。

- [ ] **Step 5: 验证三档响应式边界**

在 `2048x768`、`1280x720` 和手机窄屏下确认：

```text
按钮不被裁切
标题不与按钮重叠
元信息保持单行
元信息局部可滚动但页面无横向溢出
刷新按钮保持可见
视频和详情标签页位置不变
```

将修复前参考截图与修复后相同状态截图放在同一次视觉对照中检查。

- [ ] **Step 6: 完成最终仓库检查**

Run:

```bash
git diff --check
git status --short --branch
git log -5 --oneline
```

Expected: `git diff --check` 无输出；工作树无未提交源码改动；最近提交包含组件拆分和元信息同行实现。

不要在本任务中推送、合并或部署，除非用户随后明确授权。
