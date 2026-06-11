# KI 手机端响应式设计 — v1.0.1

**日期**: 2026-06-08
**版本**: v1.0.1
**状态**: 设计稿

---

## 目标

在现有桌面端代码基础上，通过 Tailwind 响应式断点（`md:` / `max-md:`）新增移动端 UI，桌面端零影响。

## 原则

1. **只加不改** — 所有移动端样式通过 `md:hidden` / `max-md:block` 控制，不改动现有桌面代码
2. **风格一致** — 同一套 Tailwind 变量，暗色主题 `#0B0C10` / `#141518` / `#2A2B30`
3. **断点** — `<768px` 为手机端，`≥768px` 为桌面端

---

## 架构

### 布局层 (Layout)

```
桌面端（不变）:
┌────────┬───────────────────────┐
│Sidebar │     <Outlet />        │
│ 272px  │                       │
└────────┴───────────────────────┘

手机端（新增）:
┌────────────────────────────────┐
│  Header (品牌名 + ··· 菜单)     │
├────────────────────────────────┤
│                                │
│         <Outlet />             │
│                                │
│                                │
│                            ⊕   │
├────────────────────────────────┤
│  📊     📥     💡     📄        │
│ 仪表盘  采集  脑暴  摘要       │
└────────────────────────────────┘
```

### 组件清单

| 组件 | 改动方式 |
|---|---|
| `Sidebar.tsx` | 不改 |
| `BottomTabBar.tsx` | **新建**，仅在 `md:hidden` 显示 |
| `MobileHeader.tsx` | **新建**，顶部品牌栏 + `···` 菜单 |
| `App.tsx` | 加 `MobileHeader` 和 `BottomTabBar` |
| `Ingest.tsx` | 加响应式：列表→行、tab→下拉、搜索→图标 |
| `Brainstorm.tsx` | 加响应式：列表→行、tab→下拉、搜索→图标 |
| `Dashboard.tsx` | 加响应式：4 列→2 列、图表全宽 |
| `IngestDetailPanel.tsx` | 加响应式：侧面板→全屏覆盖 |
| `BrainstormDetailPanel.tsx` | 加响应式：侧面板→全屏覆盖 |
| `Digest.tsx` | 不改（Markdown 天然响应式） |
| `SystemDoc.tsx` | 不改 |

---

## 详细设计

### 1. BottomTabBar（新建）

```
固定在底部，4 个图标+文字，当前页高亮。

<nav class="fixed bottom-0 w-full bg-[#141518] border-t border-[#2A2B30] md:hidden">
  <NavLink to="/">        <LayoutDashboard /> 仪表盘 </NavLink>
  <NavLink to="/ingest">  <Upload /> 采集        </NavLink>
  <NavLink to="/brainstorm"><Lightbulb /> 脑暴    </NavLink>
  <NavLink to="/digest">  <FileText /> 摘要       </NavLink>
</nav>
```

- 高度 56px（含 safe-area-inset-bottom）
- 每个 tab flex-1 居中
- active 状态白色文字，非 active 灰色

### 2. MobileHeader（新建）

```
固定顶部，左侧品牌名，右侧 ··· 按钮。

<header class="sticky top-0 bg-[#0B0C10] border-b border-[#2A2B30] md:hidden">
  <span>知识情报中心 <span>v1.0.1</span></span>
  <button>···</button>   ← 弹出菜单: 系统说明 / API 文档
</header>
```

- 高度 48px
- 品牌名 + 版本胶囊（同侧栏顶部）
- `···` 弹出 `Portal` 下拉菜单

### 3. 列表响应式

**现有桌面代码**: 表格布局（多列 `table` / `grid`）

**新增移动端**: 紧凑行列表

```
桌面：<table> 或 grid-cols-*（不改）
手机：flex-col 紧凑行

每条记录:
┌──────────────────────────────────┐
│  标题文字（截断）     来源标签    │
│                           14:30  │
└──────────────────────────────────┘
```

实现方式：在现有列表容器上加 `max-md:flex-col`，每条记录用 `max-md:flex max-md:flex-wrap` 改为手机行布局。

长按事件：`onTouchStart` + 计时器 → 进入选择模式 → 行左侧出现 checkbox → 底部出现"删除所选"栏。

### 4. Tab 筛选响应式

桌面横向 tab 不改。手机端 `md:hidden` 替换为 `<select>` 下拉：

```jsx
{/* 桌面 tab — 不动 */}
<div className="hidden md:flex">...</div>

{/* 手机下拉 */}
<select className="md:hidden bg-[#141518] ...">
  <option>格局 · 地缘政治</option>
  <option>财富 · 经济金融</option>
  <option>认知 · 思维模型</option>
  <option>前瞻 · 科技趋势</option>
  <option>即时快报</option>
</select>
```

### 5. 搜索响应式

桌面搜索框不改。手机端替换为图标+展开：

```jsx
{/* 桌面搜索 */}
<input className="hidden md:block" ... />

{/* 手机搜索图标 */}
<button className="md:hidden" onClick={() => setShowSearch(true)}>🔍</button>
{showSearch && <input autoFocus className="md:hidden" ... />}
```

### 6. 详情面板响应式

桌面端侧面板不动。手机端全屏覆盖：

```
桌面: fixed right-0 w-[420px]   ← 不改
手机: fixed inset-0 z-50        ← 新增

顶部: ← 返回箭头 + 标题
内容: 可滚动区
```

### 7. 悬浮按钮（FAB）

```
<button class="fixed bottom-20 right-4 z-40 md:hidden
  w-14 h-14 rounded-full bg-indigo-500 text-white shadow-lg">
  ⊕
</button>
```

仅在内容采集页和头脑风暴页显示。点开展开菜单（提交抖音 / 上传文件 / 新建问题）。

### 8. 仪表盘响应式

- 指标卡片: `grid-cols-4` → `max-md:grid-cols-2`
- 趋势图: 全宽，高度从 300px 减小到 200px
- 热力图: 全宽，cell 缩小

### 9. 摘要页

不改。Markdown 内容自动适应屏幕宽度。

---

## 样式继承

所有移动端组件使用与桌面端相同的 Tailwind class 体系：

| 用途 | Class |
|---|---|
| 页面底色 | `bg-[#0B0C10]` |
| 面板/卡片 | `bg-[#141518]` |
| 边框 | `border-[#2A2B30]` |
| 主文字 | `text-white` |
| 次文字 | `text-gray-400` |
| 强调/链接 | `text-indigo-400` |
| 成功 | `text-green-400` |
| 错误 | `text-red-400` |

---

## 不做的

- 不新建独立 mobile 项目
- 不动后端 API
- 不引入新依赖
- 不改构建配置
- 不破坏现有桌面端任何页面

---

## 验收标准

1. 桌面端（≥768px）：所有页面与改造前完全一致
2. 手机端视口（<768px）：底部 TabBar 可见，导航正常
3. 手机端列表为紧凑行布局
4. 手机端点内容 → 全屏详情，有返回箭头
5. 手机端右下角 ⊕ 按钮可正常创建
6. 手机端 tab 筛选为下拉
7. 手机端搜索为点击展开
8. 长按可进入多选模式并删除
9. 仪表盘 2x2 卡片+全宽图表
10. 配色/风格与桌面一致
