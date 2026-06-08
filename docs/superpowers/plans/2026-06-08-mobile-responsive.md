# 手机端响应式设计 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有桌面端 KI 前端基础上，通过 Tailwind 响应式断点新增移动端 UI，桌面端零影响。

**Architecture:** 新建 BottomTabBar 和 MobileHeader 组件，在 App.tsx 中加入布局；各页面加 `max-md:` 前缀的响应式分支——列表变紧凑行、tab 变下拉、搜索变图标、面板变全屏、右下角 FAB 悬浮按钮。

**Tech Stack:** React 18 + TypeScript + Tailwind CSS 4 + Vite + lucide-react

---

## 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `frontend/src/components/BottomTabBar.tsx` | 新建 | 底部 4 icon TabBar，仅在 md:hidden |
| `frontend/src/components/MobileHeader.tsx` | 新建 | 顶部品牌栏 + ··· 菜单，仅在 md:hidden |
| `frontend/src/App.tsx` | 修改 | 嵌入 MobileHeader + BottomTabBar |
| `frontend/src/pages/Ingest.tsx` | 修改 | 加响应式：列表→行、tab→下拉、搜索→图标、FAB |
| `frontend/src/pages/Brainstorm.tsx` | 修改 | 加响应式：列表→行、tab→下拉、搜索→图标、FAB |
| `frontend/src/pages/Dashboard.tsx` | 修改 | 卡片 4→2 列、图表全宽 |
| `frontend/src/pages/panels/IngestDetailPanel.tsx` | 修改 | 全屏覆盖 |
| `frontend/src/pages/panels/BrainstormDetailPanel.tsx` | 修改 | 全屏覆盖 |

---

### Task 1: BottomTabBar 组件

**Files:**
- Create: `app/frontend/src/components/BottomTabBar.tsx`

- [ ] **Step 1: 创建 BottomTabBar.tsx**

```typescript
import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, Lightbulb, FileText } from 'lucide-react';

const tabs = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/ingest', icon: Upload, label: '采集' },
  { to: '/brainstorm', icon: Lightbulb, label: '脑暴' },
  { to: '/digest', icon: FileText, label: '摘要' },
];

export default function BottomTabBar() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-[#141518] border-t border-[#2A2B30] flex items-center justify-around"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)', height: 'calc(56px + env(safe-area-inset-bottom, 0px))' }}>
      {tabs.map(tab => {
        const Icon = tab.icon;
        return (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-0.5 flex-1 h-full transition-colors ${
                isActive ? 'text-white' : 'text-gray-500'
              }`
            }
          >
            <Icon size={20} />
            <span className="text-[10px] leading-none">{tab.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 2: 验证编译**

Run: `cd app/frontend && npx tsc --noEmit`
Expected: 无新错误

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/components/BottomTabBar.tsx
git commit -m "feat: add BottomTabBar mobile component"
```

---

### Task 2: MobileHeader 组件

**Files:**
- Create: `app/frontend/src/components/MobileHeader.tsx`

- [ ] **Step 1: 创建 MobileHeader.tsx**

```typescript
import React, { useState, useRef, useEffect } from 'react';
import { MoreHorizontal, BookOpen, Code2 } from 'lucide-react';

export default function MobileHeader() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  return (
    <header className="md:hidden sticky top-0 z-30 bg-[#0B0C10] border-b border-[#2A2B30] flex items-center justify-between px-4 h-12 shrink-0">
      <div className="flex items-baseline gap-1.5">
        <span className="font-semibold text-white text-base">知识情报中心</span>
        <span className="text-[10px] text-gray-500 bg-[#2A2B30] px-1 py-0.5 rounded-full leading-none">v1.0.0</span>
      </div>
      <div ref={menuRef} className="relative">
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="p-1 rounded text-gray-400 hover:text-white"
        >
          <MoreHorizontal size={20} />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 w-36 bg-[#141518] border border-[#2A2B30] rounded-lg shadow-xl py-1 z-50">
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <Code2 size={14} />
              <span>API 文档</span>
            </a>
            <a
              href="/system"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <BookOpen size={14} />
              <span>系统说明</span>
            </a>
          </div>
        )}
      </div>
    </header>
  );
}
```

- [ ] **Step 2: 验证编译**

Run: `cd app/frontend && npx tsc --noEmit`
Expected: 无新错误

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/components/MobileHeader.tsx
git commit -m "feat: add MobileHeader component with overflow menu"
```

---

### Task 3: App.tsx 集成 MobileHeader + BottomTabBar

**Files:**
- Modify: `app/frontend/src/App.tsx`

- [ ] **Step 1: 修改 App.tsx**

将现有 Layout 改名为 DesktopLayout，新建 MobileLayout，然后 App 统一组合。

```typescript
import React from 'react';
import { Routes, Route, Outlet } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import BottomTabBar from './components/BottomTabBar';
import MobileHeader from './components/MobileHeader';
import ErrorBoundary from './components/ErrorBoundary';
import { EventCacheProvider } from './components/EventCache';
import Dashboard from './pages/Dashboard';
import Ingest from './pages/Ingest';
import Events from './pages/Events';
import Sources from './pages/Sources';
import Digest from './pages/Digest';
import Brainstorm from './pages/Brainstorm';
import SystemDoc from './pages/SystemDoc';

function DesktopLayout() {
  return (
    <div className="hidden md:flex h-screen w-full bg-[#0B0C10] overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <div className="flex-1 overflow-auto custom-scrollbar">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}

function MobileLayout() {
  return (
    <div className="md:hidden flex flex-col h-screen w-full bg-[#0B0C10] overflow-hidden font-sans">
      <MobileHeader />
      <div className="flex-1 overflow-auto custom-scrollbar">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </div>
      <BottomTabBar />
    </div>
  );
}

export default function App() {
  return (
    <EventCacheProvider>
      <Routes>
        <Route element={<DesktopLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="ingest" element={<Ingest />} />
          <Route path="events" element={<Events />} />
          <Route path="sources" element={<Sources />} />
          <Route path="digest" element={<Digest />} />
          <Route path="brainstorm" element={<Brainstorm />} />
          <Route path="system" element={<SystemDoc />} />
        </Route>
        <Route element={<MobileLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="ingest" element={<Ingest />} />
          <Route path="events" element={<Events />} />
          <Route path="sources" element={<Sources />} />
          <Route path="digest" element={<Digest />} />
          <Route path="brainstorm" element={<Brainstorm />} />
          <Route path="system" element={<SystemDoc />} />
        </Route>
      </Routes>
    </EventCacheProvider>
  );
}
```

- [ ] **Step 2: 验证编译**

Run: `cd app/frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: 桌面端验证**

Run: 浏览器打开 `http://127.0.0.1:9120`，所有页面正常展示，侧栏正常工作

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/App.tsx
git commit -m "feat: integrate MobileHeader + BottomTabBar into App layout"
```

---

### Task 4: Ingest.tsx 手机端响应式（列表 + tab + 搜索 + FAB）

**Files:**
- Modify: `app/frontend/src/pages/Ingest.tsx`

- [ ] **Step 1: 修改 header — 按钮在手机端隐藏**

在第 244-251 行，给两个按钮加 `hidden md:flex`：

```typescript
<div className="hidden md:flex gap-2">
  <button onClick={() => openModal('douyin')} className="px-4 py-2 rounded-lg text-sm font-medium bg-pink-500/20 text-pink-400 hover:bg-pink-500/30 border border-pink-500/30 transition-colors">
    抖音分享
  </button>
  <button onClick={() => openModal('file')} className="px-4 py-2 rounded-lg text-sm font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 border border-cyan-500/30 transition-colors">
    上传文件
  </button>
</div>
```

- [ ] **Step 2: Tab 切换 — 加手机下拉**

在第 261-279 行的 tab 区域，包裹为：

在第 279 行 `</div>`（tab 外层 div 结束）后，紧接着添加手机下拉：

```typescript
{/* 桌面 tab — 不动 */}
<div className="hidden md:block border-b border-[#2A2B30] mb-6">
  <div className="flex gap-6 overflow-x-auto">
    {([
      { key: '格局' as const, label: '格局', sub: '地缘政治·大国博弈·国际关系' },
      { key: '财富' as const, label: '财富', sub: '经济金融·商业洞察·投资理财' },
      { key: '认知' as const, label: '认知', sub: '思维模型·方法论·底层逻辑' },
      { key: '前瞻' as const, label: '前瞻', sub: '科技趋势·未来预判·前沿动态' },
      { key: 'briefing' as const, label: '即时快报', sub: '' },
    ]).map(t => (
      <button key={t.key} onClick={() => { setHistoryTab(t.key); setPage(1); setExpandedId(null); }}
        className={`pb-3 text-sm font-medium transition-colors relative whitespace-nowrap ${historyTab === t.key ? 'text-white' : 'text-gray-500 hover:text-gray-300'}`}>
        <div>{t.label}</div>
        {t.sub && <div className="text-[10px] text-gray-500 mt-0.5 font-normal">{t.sub}</div>}
        {historyTab === t.key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500" />}
      </button>
    ))}
  </div>
</div>

{/* 手机下拉 */}
<select
  className="md:hidden w-full mb-4 px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white focus:outline-none focus:border-purple-500/50"
  value={historyTab}
  onChange={e => { setHistoryTab(e.target.value as any); setPage(1); setExpandedId(null); }}
>
  <option value="格局">格局 · 地缘政治·大国博弈·国际关系</option>
  <option value="财富">财富 · 经济金融·商业洞察·投资理财</option>
  <option value="认知">认知 · 思维模型·方法论·底层逻辑</option>
  <option value="前瞻">前瞻 · 科技趋势·未来预判·前沿动态</option>
  <option value="briefing">即时快报</option>
</select>
```

- [ ] **Step 3: 列表 — 手机端紧凑行布局**

第 292-323 行的事件列表区域。在现有的 `md:grid` 表格下加手机端行布局。

在第 292 行 `<div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">` 之后，手机列表替换表格为紧凑行。

需要修改该区域结构：桌面保持 `md:grid grid-cols-12`，手机用 `max-md:flex max-md:flex-col`：

```typescript
<div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
  {/* 桌面表头 — 不动 */}
  <div className="hidden md:grid grid-cols-12 gap-4 px-5 py-3 text-sm text-gray-500 border-b border-[#2A2B30] items-center">
    <div className="col-span-1"></div>
    <div className="col-span-6">标题</div>
    <div className="col-span-2 text-center">来源</div>
    <div className="col-span-2 text-center">提交时间</div>
    <div className="col-span-1 text-center">操作</div>
  </div>
  {/* 桌面行 + 手机行 */}
  <div className="max-md:divide-y max-md:divide-[#2A2B30]">
  {events.map(evt => (
    <React.Fragment key={evt.id}>
      {/* 桌面行 — 不动 */}
      <div onClick={() => { if (window.getSelection()?.toString()) return; toggleSelect(evt.id); }}
        className={`hidden md:grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-[#1A1B20] transition-colors cursor-pointer border-b border-[#2A2B30] last:border-b-0 ${evt.status === 'processing' ? 'opacity-60' : ''}`}>
        <div className="col-span-1 flex justify-center" onClick={e => e.stopPropagation()}>
          <Checkbox checked={selectedIds.has(evt.id)} onChange={() => toggleSelect(evt.id)} />
        </div>
        <div className="col-span-6 min-w-0">
          <div className="text-sm text-gray-200 truncate font-medium">{evt.title}</div>
        </div>
        <div className="col-span-2 text-center">
          <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
        </div>
        <div className="col-span-2 text-center text-xs text-gray-500">{formatTimeBeijing(evt.created_at)}</div>
        <div className="col-span-1 flex justify-center gap-0.5" onClick={e => e.stopPropagation()}>
          <button onClick={() => openDetail(evt.id)} className="p-1.5 rounded text-gray-500 hover:text-purple-400 hover:bg-[#2A2B30]" title="详情">
            <Maximize2 size={15} />
          </button>
          <button onClick={(e) => handleDelete(evt.id, e)} className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-[#2A2B30]" title="删除">
            <Trash2 size={15} />
          </button>
        </div>
      </div>
      {/* 手机行 — 紧凑列表 */}
      <div
        onClick={() => openDetail(evt.id)}
        className="md:hidden flex items-center gap-3 px-4 py-3 hover:bg-[#1A1B20] transition-colors cursor-pointer active:bg-[#2A2B30]"
        onTouchStart={() => {
          // long press to enter select mode
          // TODO in next step
        }}
      >
        <div className="flex-1 min-w-0">
          <div className="text-sm text-gray-200 truncate">{evt.title}</div>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
          </div>
        </div>
        <div className="text-[10px] text-gray-500 shrink-0">{formatTimeBeijing(evt.created_at).slice(-8)}</div>
      </div>
    </React.Fragment>
  ))}
  </div>
</div>
```

注意：需要把 `events.map` 内部用 `<React.Fragment>` 包裹，因为桌面行和手机行是两个同级 div。

- [ ] **Step 4: 搜索 — 手机图标展开**

第 366-372 行搜索区域。添加 `hidden md:block` 给现有搜索框，加手机搜索图标：

```typescript
{/* Search + Batch delete + Pagination — only for history tabs */}
{historyTab !== 'briefing' && (
<div className="flex items-center justify-between mt-4 text-sm">
  {/* 桌面搜索 */}
  <div className="relative w-52 hidden md:block">
    <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
    <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="搜索..."
      className="w-full pl-8 pr-3 py-1.5 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50" />
  </div>
  {/* 手机搜索图标 */}
  <button
    className="md:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30]"
    onClick={() => {
      // toggle a mobile search state — add to component state
      setShowMobileSearch(!showMobileSearch);
    }}
  >
    <Search size={16} />
  </button>
  {/* 批量删除 — 桌面 */}
  <div className="hidden md:block">
    {selectedIds.size > 0 && (
      <button onClick={handleBatchDelete} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-colors">
        删除选中 ({selectedIds.size})
      </button>
    )}
  </div>
  {/* 分页 */}
  <div className="flex items-center gap-1 text-gray-400">
    <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1}
      className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronLeft size={16} /></button>
    <span className="text-xs">{page}/{Math.max(1, Math.ceil(total / PAGE_SIZE))}</span>
    <button onClick={() => setPage(p => p+1)} disabled={page * PAGE_SIZE >= total}
      className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronRight size={16} /></button>
  </div>
</div>
)}
```

同时需要在组件顶部添加 `showMobileSearch` state：

```typescript
const [showMobileSearch, setShowMobileSearch] = useState(false);
```

并在 footer 上方添加手机搜索展开输入框：

```typescript
{/* 手机搜索展开 */}
{showMobileSearch && (
  <div className="md:hidden mt-3">
    <input
      autoFocus
      value={search}
      onChange={e => { setSearch(e.target.value); setPage(1); }}
      placeholder="搜索标题..."
      className="w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
    />
  </div>
)}
```

- [ ] **Step 5: FAB 悬浮按钮**

在 return 末尾，`</>` 之前，添加 FAB：

```typescript
{/* 手机端 FAB */}
<div className="md:hidden fixed bottom-20 right-4 z-30 flex flex-col gap-2">
  <button
    onClick={() => openModal('douyin')}
    className="w-12 h-12 rounded-full bg-pink-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
    title="抖音分享"
  >
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
  </button>
  <button
    onClick={() => openModal('file')}
    className="w-12 h-12 rounded-full bg-cyan-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
    title="上传文件"
  >
    <Upload size={18} />
  </button>
</div>
```

- [ ] **Step 5b: 长按进入选择模式**

添加手机端 state：

```typescript
const [mobileSelectMode, setMobileSelectMode] = useState(false);
const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
```

修改手机行（Step 3 中的 compact list 行），加上长按手势：

```typescript
{/* 手机行 — 紧凑列表 */}
<div
  onClick={() => {
    if (mobileSelectMode) {
      toggleSelect(evt.id);
    } else {
      openDetail(evt.id);
    }
  }}
  onTouchStart={() => {
    longPressTimer.current = setTimeout(() => {
      setMobileSelectMode(true);
      toggleSelect(evt.id);
    }, 500);
  }}
  onTouchEnd={() => {
    if (longPressTimer.current) clearTimeout(longPressTimer.current);
  }}
  onTouchMove={() => {
    if (longPressTimer.current) clearTimeout(longPressTimer.current);
  }}
  className={`md:hidden flex items-center gap-3 px-4 py-3 hover:bg-[#1A1B20] transition-colors cursor-pointer active:bg-[#2A2B30] ${selectedIds.has(evt.id) ? 'bg-purple-500/10' : ''}`}
>
  {mobileSelectMode && (
    <Checkbox checked={selectedIds.has(evt.id)} onChange={() => toggleSelect(evt.id)} />
  )}
  <div className="flex-1 min-w-0">
    <div className="text-sm text-gray-200 truncate">{evt.title}</div>
    <div className="flex items-center gap-2 mt-1">
      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
    </div>
  </div>
  <div className="text-[10px] text-gray-500 shrink-0">{formatTimeBeijing(evt.created_at).slice(-8)}</div>
</div>
```

手机端批量删除按钮（在选择模式下显示在底部）：

```typescript
{/* 手机批量删除栏 */}
{mobileSelectMode && selectedIds.size > 0 && (
  <div className="md:hidden fixed bottom-20 left-4 right-4 z-30 bg-[#141518] border border-[#2A2B30] rounded-xl px-4 py-3 flex items-center justify-between shadow-2xl">
    <span className="text-sm text-gray-300">已选 {selectedIds.size} 条</span>
    <div className="flex gap-2">
      <button onClick={() => { setMobileSelectMode(false); setSelectedIds(new Set()); }}
        className="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white">取消</button>
      <button onClick={handleBatchDelete}
        className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20">
        删除
      </button>
    </div>
  </div>
)}
```

退出选择模式的逻辑：当 `mobileSelectMode` 为 true 且 `selectedIds.size === 0` 时自动退出（在 `toggleSelect` 中处理）。在 toggleSelect 后添加：

```typescript
function toggleSelect(id: string) {
  setSelectedIds(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
}
```

并在 useEffect 中监听 selectedIds 变化来自动关闭：

```typescript
useEffect(() => {
  if (mobileSelectMode && selectedIds.size === 0) {
    setMobileSelectMode(false);
  }
}, [selectedIds, mobileSelectMode]);
```

把两个 FAB 做成独立按钮（不合并为弹出菜单，减少交互步骤），分别触发抖音模窗和文件上传模窗。

- [ ] **Step 6: 验证编译 + 构建**

```bash
cd app/frontend && npx tsc --noEmit && npm run build
```

Expected: 构建成功

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/pages/Ingest.tsx
git commit -m "feat: add mobile responsive layout to Ingest page"
```

---

### Task 5: Brainstorm.tsx 手机端响应式

**Files:**
- Modify: `app/frontend/src/pages/Brainstorm.tsx`

- [ ] **Step 1: 新建入口 — 手机端 FAB**

参照 Ingest.tsx 的 FAB，在 Brainstorm 页添加：

```typescript
{/* 手机端 FAB */}
<button
  onClick={() => setShowCreate(true)}
  className="md:hidden fixed bottom-20 right-4 z-30 w-12 h-12 rounded-full bg-amber-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
>
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
</button>
```

- [ ] **Step 2: Tab — 手机下拉**

找到 tab 区域（约第 150 行后的 render），桌面 tab 加 `hidden md:flex`，新增手机下拉：

```typescript
{/* 桌面 tab */}
<div className="hidden md:flex gap-1 bg-[#141518] rounded-lg p-1">...</div>

{/* 手机 tab 下拉 */}
<select
  className="md:hidden w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white focus:outline-none focus:border-purple-500/50 mb-4"
  value={tab}
  onChange={e => { setTab(e.target.value as any); setPage(1); }}
>
  <option value="all">全部问题</option>
  <option value="open">待回答</option>
  <option value="done">已回答</option>
</select>
```

- [ ] **Step 3: 搜索 — 手机图标展开**

同 Ingest 模式：

```typescript
// 组件顶部添加 state
const [showSearch, setShowSearch] = useState(false);

// 搜索区域改为:
<div className="relative w-52 hidden md:block">...现有...</div>
<button className="md:hidden p-2 rounded text-gray-400" onClick={() => setShowSearch(!showSearch)}>
  <Search size={16} />
</button>
{showSearch && (
  <input autoFocus className="md:hidden w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white mt-2" ... />
)}
```

- [ ] **Step 4: 列表 — 手机紧凑行**

问题列表区域（约第 220 行后），参照 Ingest 的桌面/手机双布局模式。表格头的 `hidden md:grid` 和每行的 `grid-cols-*` 保持不变，新增手机行：

```typescript
{/* 手机行 */}
<div className="md:hidden flex items-center gap-3 px-4 py-3 hover:bg-[#1A1B20] border-b border-[#2A2B30] last:border-b-0 cursor-pointer"
  onClick={() => setSelected(q)}
>
  <div className="flex-1 min-w-0">
    <div className="text-sm text-gray-200 truncate">{q.question}</div>
    <div className="flex items-center gap-2 mt-1">
      {q.title && <span className="text-[10px] text-gray-500 truncate">{q.title}</span>}
      <span className={`text-[10px] px-1.5 py-0.5 rounded ${q.status === 'done' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'}`}>
        {q.status === 'done' ? '已回答' : '待回答'}
      </span>
    </div>
  </div>
  <ChevronRight size={14} className="text-gray-600 shrink-0" />
</div>
```

- [ ] **Step 5: 验证 + 构建**

```bash
cd app/frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/Brainstorm.tsx
git commit -m "feat: add mobile responsive layout to Brainstorm page"
```

---

### Task 6: Dashboard.tsx 手机端响应式

**Files:**
- Modify: `app/frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: 指标卡片 grid-cols 响应式**

第 55 行，把 `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` 改为：

```typescript
<div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
```

手机上 2 列，小屏 2 列，大屏 3 列。

- [ ] **Step 2: 页面容器 padding 减小**

第 32 行，`p-4 md:p-8` 已经 OK（手机 p-4），不需改动。

- [ ] **Step 3: 底部留白（避免被 TabBar 遮挡）**

在 `</div>` (最外层 max-w-7xl) 之前加：

```typescript
<div className="md:hidden h-20" />
```

- [ ] **Step 4: 验证 + 构建**

```bash
cd app/frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/pages/Dashboard.tsx
git commit -m "feat: add mobile responsive layout to Dashboard page"
```

---

### Task 7: IngestDetailPanel 手机端全屏覆盖

**Files:**
- Modify: `app/frontend/src/pages/panels/IngestDetailPanel.tsx`

- [ ] **Step 1: 面板宽度 — 手机全屏**

第 183-184 行的 `style` 改为响应式。目前 `width: '100%', maxWidth: '42rem'` 在手机上就是全宽，实际已 OK。只需去掉 backdrop（手机不需半透明遮罩因为已经全屏），加返回箭头替代 X：

在第 183 行，修改面板为：

```typescript
<>
  {/* Backdrop — 桌面有，手机无 */}
  <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} />
  <div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">
```

同时在 header 区域（第 186-194 行），X 按钮改为：

```typescript
<div ref={headerRef} className="p-4 pb-3 shrink-0">
  <div className="flex items-start justify-between">
    {/* 手机返回箭头 */}
    <button onClick={onClose} className="md:hidden p-1 -ml-1 rounded text-gray-400 hover:text-white mr-2">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
    </button>
    <div className="flex-1 min-w-0">
      <h2 className="text-white text-base md:text-lg font-semibold leading-relaxed line-clamp-2">{detail.title}</h2>
    </div>
    <button onClick={onClose} className="hidden md:block p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] shrink-0 ml-3">
      <X size={18} />
    </button>
  </div>
```

- [ ] **Step 2: 底部留白**

在内容区末尾加：

```typescript
<div className="md:hidden h-16" />
```

- [ ] **Step 3: 验证 + 构建**

```bash
cd app/frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/pages/panels/IngestDetailPanel.tsx
git commit -m "feat: full-screen mobile overlay for IngestDetailPanel"
```

---

### Task 8: BrainstormDetailPanel 手机端全屏覆盖

**Files:**
- Modify: `app/frontend/src/pages/panels/BrainstormDetailPanel.tsx`

- [ ] **Step 1: 同样改法**

与 IngestDetailPanel 相同模式。修改面板容器为响应式、加手机返回箭头、底部留白。

```typescript
// 面板容器
<div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} />
<div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">

// Header 返回箭头
<button onClick={onClose} className="md:hidden p-1 -ml-1 rounded text-gray-400 hover:text-white mr-2">
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
</button>

// 底部留白
<div className="md:hidden h-16" />
```

- [ ] **Step 2: 验证 + 构建**

```bash
cd app/frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/pages/panels/BrainstormDetailPanel.tsx
git commit -m "feat: full-screen mobile overlay for BrainstormDetailPanel"
```

---

### Task 9: 全局样式 — 页面底部留白

**Files:**
- Modify: `app/frontend/src/style.css`

- [ ] **Step 1: CSS 安全区域和底部留白**

在 style.css 末尾添加：

```css
/* Mobile safe area — avoid content hidden behind BottomTabBar */
@media (max-width: 767px) {
  .pb-safe {
    padding-bottom: calc(80px + env(safe-area-inset-bottom, 0px));
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add app/frontend/src/style.css
git commit -m "style: add mobile safe-area bottom padding"
```

---

### Task 10: 全量验证

- [ ] **Step 1: 构建前端**

```bash
cd app/frontend && npm run build
```
Expected: 构建成功

- [ ] **Step 2: 重启后端**

```bash
cd app && python -m uvicorn backend.main:app --host 0.0.0.0 --port 9120 &
```

- [ ] **Step 3: 桌面端全量验证**

浏览器打开 `http://127.0.0.1:9120`，逐一验证：

- [ ] 侧栏正常显示
- [ ] 仪表盘 4 列卡片 + 趋势图 + 热力图
- [ ] 内容采集表格式列表正确
- [ ] 点击内容 → 侧边详情面板滑出
- [ ] 头脑风暴表格式列表正确
- [ ] 摘要页正常
- [ ] 系统说明页正常
- [ ] 所有按钮/操作正常工作

- [ ] **Step 4: 手机端验证（Chrome DevTools Device Mode）**

按 F12 → 切换设备工具栏 → 选 iPhone 14 Pro (393×852)

- [ ] 侧栏消失，BottomTabBar 可见
- [ ] MobileHeader 品牌名 + ··· 菜单
- [ ] 仪表盘 2x2 卡片
- [ ] 内容采集 — tab 变下拉、搜索变图标、列表为紧凑行
- [ ] 点内容 → 全屏详情覆盖、有返回箭头
- [ ] FAB 右下角两个按钮正常
- [ ] 头脑风暴 — tab 变下拉、列表紧凑行
- [ ] 点问题 → 全屏详情覆盖
- [ ] 摘要页正常阅读
- [ ] 配色/风格与桌面一致

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: final verification — mobile responsive design complete"
```

- [ ] **Step 6: 打 tag**

```bash
git tag v1.0.1
```
