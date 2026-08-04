# 处理队列任务信息同行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将处理队列的标题、任务级文案、运行状态、北京时间和操作按钮放在同一排，同时保持节点轨道及其响应式行为不变。

**Architecture:** 在 `GlobalDockQueueOverlay` 内增加四种任务级文案映射，并用一个摘要容器包住现有标题、状态、时间和操作。CSS 将任务行收敛为“状态图标 + 内容”两列，由摘要容器承担单行弹性布局；节点轨道继续从第二列开始跨至行末。

**Tech Stack:** React 19、TypeScript 6、CSS、Node.js 原生测试、Vite 8

---

### Task 1: 锁定任务摘要结构和响应式规则

**Files:**
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs:106-190`

- [ ] **Step 1: 写入失败的组合回归测试**

在现有队列轨道测试后增加：

```js
test('queue task summary keeps title, lifecycle, runtime, time, and actions on one line', () => {
  const dockQueueOverlay = readFileSync(dockQueueOverlayUrl, 'utf8');
  const summaryStart = dockQueueOverlay.indexOf('<div className="global-dock-queue-summary">');
  const summaryEnd = dockQueueOverlay.indexOf('</div>', summaryStart);
  const summary = dockQueueOverlay.slice(summaryStart, summaryEnd);

  assert.match(dockQueueOverlay, /const TASK_STATUS_LABELS: Record<QueueItem\['status'\], string> = \{[\s\S]*running: '处理中'[\s\S]*pending: '等待处理'[\s\S]*error: '处理异常'[\s\S]*done: '处理完成'/);
  assert.match(dockQueueOverlay, /const taskMessage = item\.error \|\| TASK_STATUS_LABELS\[item\.status\];/);
  assert.ok(summaryStart >= 0 && summaryEnd > summaryStart);
  assert.match(summary, /global-dock-queue-task/);
  assert.match(summary, /global-dock-queue-message/);
  assert.match(summary, /global-dock-queue-state/);
  assert.match(summary, /formatTimeBeijing\(item\.created_at\)/);
  assert.match(summary, /global-dock-queue-actions/);
  assert.ok(summary.indexOf('global-dock-queue-task') < summary.indexOf('global-dock-queue-message'));
  assert.ok(summary.indexOf('global-dock-queue-message') < summary.indexOf('global-dock-queue-state'));
  assert.ok(summary.indexOf('global-dock-queue-state') < summary.indexOf('formatTimeBeijing'));
  assert.ok(summary.indexOf('formatTimeBeijing') < summary.indexOf('global-dock-queue-actions'));
  assert.match(summary, /title=\{title\}/);
  assert.match(summary, /title=\{taskMessage\}/);
});

test('queue task summary has stable desktop and compact geometry', () => {
  const desktopSummary = dockQueueCss.match(/\.global-dock-queue-summary \{[\s\S]*?\n\}/)?.[0] || '';
  const desktopTask = dockQueueCss.match(/\.global-dock-queue-task \{[\s\S]*?\n\}/)?.[0] || '';
  const desktopMessage = dockQueueCss.match(/\.global-dock-queue-message \{[\s\S]*?\n\}/)?.[0] || '';
  const mobileCss = cssBlockBody(dockQueueCss, '@media (max-width: 760px)');

  assert.match(dockQueueCss, /\.global-dock-queue-list article \{[\s\S]*?grid-template-columns:\s*18px minmax\(0, 1fr\);/);
  assert.match(desktopSummary, /display:\s*flex;/);
  assert.match(desktopSummary, /align-items:\s*center;/);
  assert.match(desktopSummary, /min-width:\s*0;/);
  assert.match(desktopSummary, /white-space:\s*nowrap;/);
  assert.match(desktopTask, /flex:\s*1 1 auto;/);
  assert.match(desktopTask, /min-width:\s*0;/);
  assert.match(desktopMessage, /max-width:\s*32%;/);
  assert.match(desktopMessage, /text-overflow:\s*ellipsis;/);
  assert.match(dockQueueCss, /\.global-dock-queue-state,[\s\S]*?\.global-dock-queue-actions \{[\s\S]*?flex:\s*0 0 auto;/);
  assert.match(mobileCss, /\.global-dock-queue-list article \{\s*grid-template-columns:\s*16px minmax\(0, 1fr\);/);
  assert.match(mobileCss, /\.global-dock-queue-summary > em \{\s*display:\s*none;/);
  assert.doesNotMatch(mobileCss, /\.global-dock-queue-state\s*\{[^}]*display:\s*none/);
});
```

- [ ] **Step 2: 运行定向测试并确认失败**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/react-bits/dualNavigationComposition.test.mjs
```

Expected: FAIL，缺少 `TASK_STATUS_LABELS`、`.global-dock-queue-summary` 和新的两列布局。

- [ ] **Step 3: 提交失败测试**

```bash
git add app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs
git commit -m "test: define inline queue task summary"
```

### Task 2: 实现任务摘要同行布局

**Files:**
- Modify: `app/frontend/src/pages/GlobalDockQueueOverlay.tsx:21-26,107-127`
- Modify: `app/frontend/src/pages/GlobalDockQueueOverlay.css:69-113,158-167`
- Test: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: 增加任务级文案映射**

在 `STATUS_META` 后加入：

```tsx
const TASK_STATUS_LABELS: Record<QueueItem['status'], string> = {
  running: '处理中',
  pending: '等待处理',
  error: '处理异常',
  done: '处理完成',
};
```

在任务循环中、`title` 后加入：

```tsx
const taskMessage = item.error || TASK_STATUS_LABELS[item.status];
```

- [ ] **Step 2: 将五项信息放进同一摘要容器**

用下面结构替换任务图标后的标题、时间、状态和操作节点：

```tsx
<div className="global-dock-queue-summary">
  <span className="global-dock-queue-task" title={title}><b>{title}</b></span>
  <small className="global-dock-queue-message" title={taskMessage}>{taskMessage}</small>
  <span className="global-dock-queue-state">{status.label}</span>
  <em>{formatTimeBeijing(item.created_at) || '--'}</em>
  <div className="global-dock-queue-actions">
    {item.status === 'error' && (
      <button type="button" onClick={() => void retryQueueTask(item.id)} aria-label={`重试 ${title}`} title="重试" data-bento-suspend><RotateCcw /></button>
    )}
    <button type="button" onClick={() => void deleteQueueTask(item.id)} aria-label={`删除 ${title}`} title="删除" data-bento-suspend><Trash2 /></button>
  </div>
</div>
```

`<QueueProgressTrack item={item} />` 继续作为摘要容器后的兄弟节点。

- [ ] **Step 3: 将桌面任务行改为两列并实现单行摘要**

将现有任务行、标题、消息、时间、状态和操作样式替换为：

```css
.global-dock-queue-list article {
  display: grid;
  min-height: 58px;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, .055);
  color: rgba(255, 255, 255, .42);
}
.global-dock-queue-summary {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}
.global-dock-queue-task { display: block; flex: 1 1 auto; min-width: 0; }
.global-dock-queue-task b,
.global-dock-queue-message,
.global-dock-queue-summary > em {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.global-dock-queue-task b {
  display: block;
  color: rgba(255, 255, 255, .78);
  font-size: var(--dock-font-body);
  font-weight: 500;
}
.global-dock-queue-message {
  flex: 0 1 auto;
  max-width: 32%;
  color: rgba(255, 255, 255, .28);
  font-size: var(--dock-font-micro);
}
.global-dock-queue-summary > em {
  color: rgba(255, 255, 255, .28);
  font-size: var(--dock-font-micro);
  font-style: normal;
}
.global-dock-queue-state,
.global-dock-queue-summary > em,
.global-dock-queue-actions { flex: 0 0 auto; }
```

保留现有状态颜色、操作按钮和节点轨道规则。

- [ ] **Step 4: 调整窄屏规则**

将任务行和隐藏规则改为：

```css
.global-dock-queue-list article { grid-template-columns: 16px minmax(0, 1fr); }
.global-dock-queue-summary { gap: 6px; }
.global-dock-queue-summary > em { display: none; }
.global-dock-queue-message { max-width: 28%; }
```

不要隐藏 `.global-dock-queue-state`；节点轨道横向滚动规则保持不变。

- [ ] **Step 5: 运行定向测试并确认通过**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/react-bits/dualNavigationComposition.test.mjs
```

Expected: PASS，所有 `dualNavigationComposition` 子测试通过。

- [ ] **Step 6: 提交实现**

```bash
git add app/frontend/src/pages/GlobalDockQueueOverlay.tsx app/frontend/src/pages/GlobalDockQueueOverlay.css
git commit -m "fix: align queue task summary"
```

### Task 3: 完整验证与真实界面检查

**Files:**
- Verify: `app/frontend/src/pages/GlobalDockQueueOverlay.tsx`
- Verify: `app/frontend/src/pages/GlobalDockQueueOverlay.css`
- Verify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: 运行类型检查**

Run:

```bash
cd app/frontend
npm run typecheck
```

Expected: exit code 0，无 TypeScript 错误。

- [ ] **Step 2: 运行完整前端测试**

Run:

```bash
cd app/frontend
npm run test:quality-gates
npm run test:cinematic-scene
npm run test:cinematic-ingest
npm run test:media-transport
```

Expected: 所有测试通过。

- [ ] **Step 3: 运行生产构建**

Run:

```bash
cd app/frontend
npm run build
```

Expected: Vite 构建完成，exit code 0。

- [ ] **Step 4: 检查桌面端真实队列**

启动现有本地开发服务并打开 `http://127.0.0.1:5174/#/ingest`。打开“处理队列”，确认运行任务的同一排依次显示标题、处理中、运行中、北京时间和删除按钮；标题省略时状态、时间和按钮仍完整，下方节点轨道无位移。

- [ ] **Step 5: 检查窄屏真实队列**

在 390px 左右宽度检查同一任务：北京时间隐藏；标题、处理中、运行中和删除按钮保持同行；节点轨道可横向滑动并定位当前节点；页面无横向溢出。

- [ ] **Step 6: 检查工作树并提交必要的验证修正**

Run:

```bash
git diff --check
git status --short
```

Expected: 无空白错误，只包含本计划内文件；若真实界面检查产生必要修正，单独提交：

```bash
git add app/frontend/src/pages/GlobalDockQueueOverlay.tsx app/frontend/src/pages/GlobalDockQueueOverlay.css app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs
git commit -m "fix: refine queue task summary responsiveness"
```
