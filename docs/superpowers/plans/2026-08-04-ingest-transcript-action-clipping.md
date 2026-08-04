# 内容详情转写处理按钮裁切修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除嵌入式内容详情阅读区的水平溢出，使“转写处理”按钮和转写状态完整显示。

**Architecture:** 保留现有 React 结构和详情标题弹性布局，只在嵌入式内容详情的 CSS 边界中修正 `.ingest-detail-reader` 的盒模型。通过现有组合测试锁定 `width: 100%` 必须配合 `border-box`，再用真实浏览器几何测量确认子元素右边界不超过详情面板。

**Tech Stack:** React 19、TypeScript 6、Vite 8、CSS、Node.js 内置测试运行器、Chrome 浏览器验证

---

## 文件结构

- 修改 `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`：增加嵌入式详情阅读区盒模型契约。
- 修改 `app/frontend/src/pages/DualNavigationDemo.css`：让详情阅读区的 `100%` 宽度包含自身盒模型尺寸。
- 不修改 `ContentDetailPanel.tsx` 和 `TranscriptActions.tsx`：现有标题、按钮和状态 DOM 结构保持不变。

### Task 1: 用测试锁定并修复详情阅读区水平溢出

**Files:**
- Test: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: 写入失败的 CSS 契约测试**

在 `formal ingest composes a split list orbit and reusable detail workspace` 测试中，紧接现有 `.ingest-detail-reader` 宽度断言后增加：

```js
  assert.match(
    shellCss,
    /\.ki-ingest-detail-pane \.ingest-detail-reader\s*\{[^}]*box-sizing:\s*border-box\s*!important/s,
  );
```

该断言要求详情阅读区把 `width: 100%`、内容和自身尺寸统一计算在父容器可用宽度内。

- [ ] **Step 2: 运行定向测试并确认红灯**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: FAIL；失败位置为新增的 `box-sizing: border-box !important` 正则断言，其他已执行子测试不因语法或文件读取错误失败。

- [ ] **Step 3: 添加最小 CSS 修复**

在 `DualNavigationDemo.css` 的既有规则中加入盒模型声明：

```css
.ki-ingest-detail-pane .ingest-detail-reader {
  position: relative !important;
  inset: auto !important;
  box-sizing: border-box !important;
  width: 100% !important;
  height: 100% !important;
}
```

不要增加额外右侧内边距，不调整 `.transcript-title-row`、`.transcript-title-actions` 或 `.transcript-action-button`。

- [ ] **Step 4: 运行定向测试并确认绿灯**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: PASS；该文件所有子测试通过，进程退出码为 `0`。

- [ ] **Step 5: 检查补丁范围**

Run:

```bash
git diff --check
git diff -- app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs app/frontend/src/pages/DualNavigationDemo.css
```

Expected: `git diff --check` 无输出；差异只包含一个测试断言和一个 `box-sizing` 声明。

- [ ] **Step 6: 提交修复**

```bash
git add app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs app/frontend/src/pages/DualNavigationDemo.css
git commit -m "fix: keep transcript action inside detail pane"
```

### Task 2: 完整回归与真实窗口验证

**Files:**
- Verify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Verify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: 运行完整前端测试**

Run:

```bash
cd app/frontend
npm run test:cinematic-scene
```

Expected: 所有列出的 Node 子测试通过，进程退出码为 `0`，无失败测试。

- [ ] **Step 2: 运行类型检查和生产构建**

Run:

```bash
cd app/frontend
npm run typecheck
npm run build
```

Expected: 两条命令退出码均为 `0`；TypeScript 无错误，Vite 成功生成 `dist/`。

- [ ] **Step 3: 启动独立本地验证服务**

Run:

```bash
cd app/frontend
npm run dev -- --port 5174
```

Expected: Vite 在 `http://127.0.0.1:5174/` 提供当前工作树页面。如果该端口已被占用，改用下一个可用端口，并记录实际 URL。

- [ ] **Step 4: 在已登录浏览器复现相同内容详情**

打开本地内容采集页，选择一条包含转写的内容，并保持“转写原文”标签页激活。若本地端口没有现成登录状态，停在登录页并请用户完成本地登录，不读取或复制浏览器中的令牌。

确认页面中同时可见：内容标题、“转写处理”按钮、按钮下方转写状态、视频和四个详情标签页。

- [ ] **Step 5: 测量修复后几何边界**

在页面只读执行以下测量：

```js
const rect = (selector) => {
  const element = document.querySelector(selector);
  if (!element) return null;
  const box = element.getBoundingClientRect();
  return { left: box.left, right: box.right, width: box.width };
};

({
  pane: rect('.ki-ingest-detail-pane'),
  reader: rect('.ki-ingest-detail-pane .ingest-detail-reader'),
  actions: rect('.transcript-title-actions'),
  button: rect('.transcript-action-button'),
});
```

Expected:

```text
reader.right <= pane.right
actions.right <= pane.right
button.right <= pane.right
```

允许小于 `1px` 的浮点舍入误差。按钮文字、图标、边框和右侧留白必须完整可见，标题不得与按钮重叠。

- [ ] **Step 6: 完成视觉对照**

在用户截图对应的宽窗口和一个较窄桌面窗口分别截图。将修复前截图与本地修复后截图并排检查，确认：

```text
转写处理按钮完整
转写状态完整
标题与按钮不重叠
视频未被压缩或偏移
四个详情标签页无裁切或挤压
详情面板没有新增横向滚动
```

- [ ] **Step 7: 完成最终仓库检查**

Run:

```bash
git diff --check
git status --short --branch
git log -2 --oneline
```

Expected: `git diff --check` 无输出；工作树无未提交源码修改；最近两条提交依次为实现提交和本计划或设计提交。

不要在本任务中推送、合并或部署，除非用户随后明确授权。
