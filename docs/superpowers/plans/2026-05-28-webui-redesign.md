# WebUI 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 KnowledgeIntelligence WebUI 从单页锚点滚动重构为 React Router 驱动的多页面应用，统一组件风格，窄侧边栏图标导航。

**Architecture:** React Router v6 壳（App.tsx）+ 6 个页面组件 + 共享组件库，保持暗色 teal 主题，API 不变，纯前端重构。

**Tech Stack:** React 18, React Router DOM v6, TypeScript, Vite, CSS（无第三方 UI 库）

---

## 文件结构

```
app/frontend/src/
├── main.tsx                # 入口：BrowserRouter + App（新建，替代原来 App.tsx 的 createRoot 部分）
├── App.tsx                 # Layout shell：sidebar + <Outlet>（重写）
├── style.css               # 全局样式（精简重组）
├── components/
│   ├── MetricCard.tsx      # 指标卡片（新建）
│   ├── EventRow.tsx        # 事件列表项（新建）
│   ├── SourceRow.tsx       # 信息源行（新建）
│   ├── CandidateRow.tsx    # 候选行（新建）
│   ├── EmptyState.tsx      # 空状态（新建）
│   ├── StatusPill.tsx      # 状态标签（新建）
│   └── Sidebar.tsx         # 侧边栏导航（新建）
└── pages/
    ├── Dashboard.tsx       # /
    ├── Ingest.tsx          # /ingest
    ├── Events.tsx          # /events
    ├── Sources.tsx         # /sources
    ├── Digest.tsx          # /digest
    └── Candidates.tsx      # /candidates
```

---

### Task 1: 安装依赖 + 入口改造

**Files:**
- Modify: `app/frontend/src/App.tsx` → 删掉 `createRoot` 部分，改为 export App
- Create: `app/frontend/src/main.tsx`

- [ ] **Step 1: 安装 react-router-dom**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm install react-router-dom 2>&1
```

- [ ] **Step 2: 创建 main.tsx**

```tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './style.css';

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);
```

- [ ] **Step 3: 修改 App.tsx — 去掉 createRoot 调用**

删除文件末尾的 `createRoot(document.getElementById('root')!).render(<App />);`，将 `function App()` 保持不变。同时在文件顶部确认有 `export default App;` 或改为：

```tsx
export default function App() {
```

- [ ] **Step 4: 更新 index.html 入口引用**

```html
<script type="module" src="/src/main.tsx"></script>
```

- [ ] **Step 5: 构建验证**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

预期：构建成功，dist 生成 `index.html` + JS/CSS assets

---

### Task 2: 提取共享组件

**Files:**
- Create: `app/frontend/src/components/StatusPill.tsx`
- Create: `app/frontend/src/components/EmptyState.tsx`
- Create: `app/frontend/src/components/MetricCard.tsx`

- [ ] **Step 1: 创建 StatusPill.tsx**

```tsx
import React from 'react';

const statusLabels: Record<string, string> = {
  new: '新增',
  processing: '处理中',
  error: '失败',
  digest: '已入摘要',
  candidate: '待审核',
  accepted: '已确认',
  ignored: '已忽略',
  done: '已处理',
};

const statusColors: Record<string, string> = {
  new: 'rgba(45,212,191,0.2)',
  processing: 'rgba(96,165,250,0.2)',
  error: 'rgba(248,113,113,0.2)',
};

export default function StatusPill({ status }: { status: string }) {
  const label = statusLabels[status] ?? status;
  const bg = statusColors[status] ?? 'rgba(148,163,184,0.15)';
  return (
    <span style={{
      border: `1px solid ${bg}`,
      borderRadius: 999,
      padding: '2px 8px',
      fontSize: '0.8rem',
      color: status === 'error' ? '#fecaca' : '#ccfbf1',
      background: bg,
    }}>{label}</span>
  );
}
```

- [ ] **Step 2: 创建 EmptyState.tsx**

```tsx
import React from 'react';

export default function EmptyState({ icon, title, hint }: { icon: string; title: string; hint: string }) {
  return (
    <div style={{
      border: '1px dashed rgba(148,163,184,0.18)',
      borderRadius: 12,
      padding: '2rem',
      textAlign: 'center',
      color: '#8fb8af',
    }}>
      <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{icon}</div>
      <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{title}</div>
      <div style={{ fontSize: '0.85rem', color: '#6b8b83' }}>{hint}</div>
    </div>
  );
}
```

- [ ] **Step 3: 创建 MetricCard.tsx**

```tsx
import React from 'react';

export default function MetricCard({ icon, label, value }: { icon: string; label: string; value: number }) {
  return (
    <section style={{
      border: '1px solid rgba(148,163,184,0.15)',
      borderRadius: 12,
      padding: '0.9rem 1.1rem',
      background: 'rgba(15,23,42,0.46)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: '0.95rem' }}>{icon}</span>
        <span style={{ color: '#8fb8af', fontSize: '0.8rem' }}>{label}</span>
      </div>
      <strong style={{ display: 'block', fontSize: '1.8rem', color: '#f8fafc' }}>{value}</strong>
    </section>
  );
}
```

- [ ] **Step 4: 构建验证**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

预期：构建成功（组件暂时未被引用，TS 可能 warning，可忽略）

---

### Task 3: 侧边栏 + Layout Shell

**Files:**
- Create: `app/frontend/src/components/Sidebar.tsx`
- Modify: `app/frontend/src/App.tsx` — 重写为 layout shell

- [ ] **Step 1: 创建 Sidebar.tsx**

```tsx
import React from 'react';
import { NavLink } from 'react-router-dom';

const navItems = [
  { to: '/', icon: '📊', label: '仪表盘' },
  { to: '/ingest', icon: '📱', label: '内容摄入' },
  { to: '/events', icon: '📋', label: '事件列表' },
  { to: '/sources', icon: '📡', label: '信息源' },
  { to: '/digest', icon: '📝', label: '摘要' },
  { to: '/candidates', icon: '✅', label: '行动候选' },
];

export default function Sidebar() {
  return (
    <aside style={{
      width: 64,
      flexShrink: 0,
      borderRight: '1px solid rgba(148,163,184,0.15)',
      padding: '0.8rem 0.4rem',
      background: 'rgba(5,15,12,0.72)',
      backdropFilter: 'blur(16px)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 4,
    }}>
      <div style={{
        width: 36, height: 36,
        display: 'grid', placeItems: 'center',
        border: '1px solid rgba(45,212,191,0.45)',
        borderRadius: 10,
        color: '#5eead4',
        fontWeight: 800,
        fontSize: '0.8rem',
        marginBottom: 12,
      }}>KI</div>
      {navItems.map(item => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          title={item.label}
          style={({ isActive }) => ({
            width: 40, height: 40,
            display: 'grid', placeItems: 'center',
            borderRadius: 8,
            border: `1px solid ${isActive ? 'rgba(45,212,191,0.4)' : 'rgba(148,163,184,0.1)'}`,
            background: isActive ? 'rgba(45,212,191,0.1)' : 'transparent',
            textDecoration: 'none',
            fontSize: '1.1rem',
          })}
        >
          {item.icon}
        </NavLink>
      ))}
    </aside>
  );
}
```

- [ ] **Step 2: 重写 App.tsx 为 layout shell**

```tsx
import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './components/Sidebar';

export default function App() {
  return (
    <main style={{
      display: 'flex',
      minHeight: '100vh',
    }}>
      <Sidebar />
      <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto' }}>
        <Outlet />
      </div>
    </main>
  );
}
```

删除所有旧的 state、fetch 逻辑、旧组件和 pages 数组。

- [ ] **Step 3: 构建验证（暂时无路由，会白屏但不报错）**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

预期：构建成功，无 TypeScript 错误

---

### Task 4: 路由配置

**Files:**
- Modify: `app/frontend/src/main.tsx` — 加入 Routes

- [ ] **Step 1: 更新 main.tsx 加入路由占位**

```tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import './style.css';

// 占位页面组件（后续逐个替换）
const Placeholder = ({ title }: { title: string }) => (
  <div style={{ color: '#8fb8af', padding: '2rem' }}>
    <h2 style={{ color: '#f8fafc' }}>{title}</h2>
    <p>即将实现...</p>
  </div>
);

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />}>
        <Route index element={<Placeholder title="仪表盘" />} />
        <Route path="ingest" element={<Placeholder title="内容摄入" />} />
        <Route path="events" element={<Placeholder title="事件列表" />} />
        <Route path="sources" element={<Placeholder title="信息源" />} />
        <Route path="digest" element={<Placeholder title="摘要" />} />
        <Route path="candidates" element={<Placeholder title="行动候选" />} />
      </Route>
    </Routes>
  </BrowserRouter>
);
```

- [ ] **Step 2: 构建 + 启动验证**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

启动服务后，浏览器访问 `http://localhost:9120` → 应看到侧边栏 + 「仪表盘」的 placeholder。点击侧边栏图标 → URL 变化 + 内容切换为对应 placeholder。

预期：构建成功，路由骨架可用

---

### Task 5: 仪表盘页面 + 事件列表项组件

**Files:**
- Create: `app/frontend/src/components/EventRow.tsx`
- Create: `app/frontend/src/pages/Dashboard.tsx`
- Modify: `app/frontend/src/main.tsx` — 替换 Dashboard 路由

- [ ] **Step 1: 创建 EventRow.tsx**

从旧 App.tsx 提取 EventRow，改为使用 StatusPill：

```tsx
import React from 'react';
import StatusPill from './StatusPill';

const sourceLabels: Record<string, string> = {
  douyin: '抖音',
  'user-upload': '用户上传',
  'Al Jazeera': '半岛电视台',
  'BBC Business': 'BBC 商业',
  'BBC Technology': 'BBC 科技',
  'BBC Top Stories': 'BBC 头条',
  'BBC World': 'BBC 世界新闻',
  NPR: 'NPR',
  'Reuters World': '路透',
};

function formatSource(id: string) { return sourceLabels[id] ?? id; }

type Props = {
  id: string;
  title: string;
  url: string;
  source_id: string;
  topic: string | null;
  status: string;
  raw_summary: string | null;
  created_at: string;
};

export default function EventRow({ id, title, url, source_id, topic, status, raw_summary }: Props) {
  const preview = raw_summary
    ? raw_summary.length > 200 ? raw_summary.slice(0, 200) + '…' : raw_summary
    : '暂无摘要';
  return (
    <div style={{
      border: '1px solid rgba(148,163,184,0.12)',
      borderRadius: 8,
      padding: '0.7rem 0.9rem',
      background: 'rgba(5,15,12,0.3)',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: 12,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {url
          ? <a href={url} target="_blank" rel="noreferrer" style={{ color: '#f8fafc', fontWeight: 600, textDecoration: 'none' }}>{title}</a>
          : <strong style={{ color: '#f8fafc' }}>{title}</strong>}
        <p style={{ margin: '0.3rem 0 0', color: '#9abeb7', fontSize: '0.85rem', lineHeight: 1.4 }}>{preview}</p>
      </div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
        <span style={{ fontSize: '0.75rem', color: '#6b8b83' }}>{formatSource(source_id)}</span>
        {topic ? <span style={{ fontSize: '0.75rem', color: '#6b8b83' }}>{topic}</span> : null}
        <StatusPill status={status} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 Dashboard.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import MetricCard from '../components/MetricCard';
import EventRow from '../components/EventRow';
import EmptyState from '../components/EmptyState';

export default function Dashboard() {
  const [summary, setSummary] = useState({ today_events: 0, high_priority_events: 0, pending_candidates: 0, sources_enabled: 0 });
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/dashboard/summary').then(r => r.json()),
      fetch('/api/events').then(r => r.json()),
    ]).then(([s, e]) => {
      setSummary(s);
      setEvents((e || []).slice(0, 5));
    }).finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h2 style={{ color: '#f8fafc', margin: '0 0 1rem' }}>📊 仪表盘</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <MetricCard icon="📰" label="今日新增" value={summary.today_events} />
        <MetricCard icon="⚠️" label="高优先级" value={summary.high_priority_events} />
        <MetricCard icon="📋" label="待处理候选" value={summary.pending_candidates} />
        <MetricCard icon="📡" label="信息源" value={summary.sources_enabled} />
      </div>

      <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <Link to="/ingest" style={{
          border: '1px solid rgba(45,212,191,0.45)',
          borderRadius: 999,
          padding: '0.55rem 1rem',
          background: 'rgba(20,184,166,0.15)',
          color: '#ccfbf1',
          fontWeight: 600,
          textDecoration: 'none',
          fontSize: '0.85rem',
        }}>📱 提交抖音链接</Link>
        <Link to="/ingest" style={{
          border: '1px solid rgba(96,165,250,0.4)',
          borderRadius: 999,
          padding: '0.55rem 1rem',
          background: 'rgba(59,130,246,0.12)',
          color: '#ccfbf1',
          fontWeight: 600,
          textDecoration: 'none',
          fontSize: '0.85rem',
        }}>📁 上传文件</Link>
      </div>

      <h3 style={{ color: '#5eead4', fontSize: '0.95rem', margin: '0 0 0.5rem' }}>最近事件</h3>
      {events.length === 0
        ? <EmptyState icon="📭" title="暂无事件" hint="提交抖音链接或上传文件开始" />
        : (
          <div style={{ display: 'grid', gap: '0.5rem' }}>
            {events.map((e: any) => <EventRow key={e.id} {...e} />)}
            <Link to="/events" style={{ color: '#5eead4', fontSize: '0.85rem', textAlign: 'right' }}>
              查看全部 →
            </Link>
          </div>
        )}
    </div>
  );
}
```

- [ ] **Step 3: 更新 main.tsx，替换 Dashboard 路由**

将 `main.tsx` 中的 `<Route index element={<Placeholder title="仪表盘" />} />` 替换为：

```tsx
import Dashboard from './pages/Dashboard';
// ...
<Route index element={<Dashboard />} />
```

- [ ] **Step 4: 构建验证**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

预期：构建成功

---

### Task 6: 内容摄入页面

**Files:**
- Create: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/main.tsx` — 替换 ingest 路由

- [ ] **Step 1: 创建 Ingest.tsx**

```tsx
import React, { useState } from 'react';
import { Link } from 'react-router-dom';

type Tab = 'douyin' | 'file';

const inputStyle: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  border: '1px solid rgba(148,163,184,0.22)',
  borderRadius: 10, padding: '0.6rem 0.75rem',
  background: 'rgba(15,23,42,0.5)', color: '#d8f7f0',
  fontFamily: 'inherit', fontSize: '0.9rem',
};

export default function Ingest() {
  const [tab, setTab] = useState<Tab>('douyin');

  // Douyin
  const [douyinText, setDouyinText] = useState('');
  const [douyinTopic, setDouyinTopic] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ event_id: string; type: string } | null>(null);
  const [error, setError] = useState('');

  // File
  const [fileType, setFileType] = useState('video_file');
  const [fileTitle, setFileTitle] = useState('');
  const [fileTopic, setFileTopic] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileSubmitting, setFileSubmitting] = useState(false);
  const [fileResult, setFileResult] = useState<{ event_id: string; type: string } | null>(null);
  const [fileError, setFileError] = useState('');

  async function submitDouyin() {
    if (!douyinText.trim()) return;
    setSubmitting(true); setError(''); setResult(null);
    try {
      const res = await fetch('/api/ingest/douyin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ share_text: douyinText.trim(), topic: douyinTopic.trim() || 'uncategorized' }),
      });
      if (!res.ok) throw new Error('提交失败');
      setResult(await res.json());
      setDouyinText('');
    } catch (e: any) {
      setError(e.message);
    } finally { setSubmitting(false); }
  }

  async function submitFile() {
    if (!selectedFile) return;
    setFileSubmitting(true); setFileError(''); setFileResult(null);
    try {
      const fd = new FormData();
      fd.append('type', fileType);
      fd.append('file', selectedFile);
      fd.append('title', fileTitle.trim());
      fd.append('topic', fileTopic.trim() || 'uncategorized');
      const res = await fetch('/api/ingest/file', { method: 'POST', body: fd });
      if (!res.ok) throw new Error('上传失败');
      setFileResult(await res.json());
      setSelectedFile(null); setFileTitle('');
    } catch (e: any) {
      setFileError(e.message);
    } finally { setFileSubmitting(false); }
  }

  const tabBtn = (t: Tab, icon: string, label: string) => (
    <button onClick={() => setTab(t)} disabled={submitting || fileSubmitting} style={{
      border: `1px solid ${tab === t ? 'rgba(45,212,191,0.4)' : 'rgba(148,163,184,0.12)'}`,
      borderRadius: 10,
      padding: '0.5rem 1rem',
      background: tab === t ? 'rgba(45,212,191,0.1)' : 'transparent',
      color: tab === t ? '#5eead4' : '#8fb8af',
      cursor: 'pointer',
      fontWeight: 600,
      fontSize: '0.9rem',
    }}>{icon} {label}</button>
  );

  return (
    <div>
      <h2 style={{ color: '#f8fafc', margin: '0 0 1rem' }}>📱 内容摄入</h2>

      <div style={{ display: 'flex', gap: 8, marginBottom: '1rem' }}>{tabBtn('douyin', '📱', '抖音分享')}{tabBtn('file', '📁', '文件上传')}</div>

      {tab === 'douyin' && (
        <div style={{ maxWidth: 640 }}>
          <textarea style={{ ...inputStyle, resize: 'vertical', minHeight: 80, marginBottom: '0.5rem' } as React.CSSProperties}
            placeholder="粘贴抖音分享文字，例如：&#10;4.69 复制打开抖音，看看【xxx】的作品… https://v.douyin.com/xxxxx/"
            rows={3} value={douyinText} onChange={e => setDouyinText(e.target.value)} disabled={submitting}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input style={{ ...inputStyle, flex: 1 }} placeholder="主题标签（如 psychology）"
              value={douyinTopic} onChange={e => setDouyinTopic(e.target.value)} disabled={submitting} />
            <button onClick={submitDouyin} disabled={submitting || !douyinText.trim()} style={{
              border: '1px solid rgba(45,212,191,0.45)', borderRadius: 999,
              padding: '0.55rem 1.2rem', background: 'rgba(20,184,166,0.15)',
              color: '#ccfbf1', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem',
              whiteSpace: 'nowrap',
            }}>{submitting ? '提交中…' : '提交转写'}</button>
          </div>
          {result && <p style={{ color: '#5eead4', marginTop: '0.5rem', fontSize: '0.9rem' }}>
            ✅ 已提交：<code>{result.event_id}</code>，<Link to="/events" style={{ color: '#5eead4' }}>查看事件 →</Link>
          </p>}
          {error && <p style={{ color: '#fecaca', marginTop: '0.5rem', fontSize: '0.9rem' }}>{error}</p>}
        </div>
      )}

      {tab === 'file' && (
        <div style={{ maxWidth: 640 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: '0.5rem' }}>
            <select style={inputStyle} value={fileType} onChange={e => setFileType(e.target.value)} disabled={fileSubmitting}>
              <option value="video_file">视频文件（自动提取音频）</option>
              <option value="audio_file">音频文件</option>
              <option value="document">文档（.md / .txt）</option>
            </select>
            <input style={{ ...inputStyle, flex: 1 }} placeholder="标题（可选）"
              value={fileTitle} onChange={e => setFileTitle(e.target.value)} disabled={fileSubmitting} />
            <input style={{ ...inputStyle, flex: 1 }} placeholder="主题标签（可选）"
              value={fileTopic} onChange={e => setFileTopic(e.target.value)} disabled={fileSubmitting} />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="file" onChange={e => setSelectedFile(e.target.files?.[0] ?? null)} disabled={fileSubmitting}
              style={{ color: '#b7d7d1', fontSize: '0.85rem' }} />
            <button onClick={submitFile} disabled={fileSubmitting || !selectedFile} style={{
              border: '1px solid rgba(96,165,250,0.4)', borderRadius: 999,
              padding: '0.55rem 1.2rem', background: 'rgba(59,130,246,0.12)',
              color: '#ccfbf1', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem',
              whiteSpace: 'nowrap',
            }}>{fileSubmitting ? '上传中…' : '上传处理'}</button>
          </div>
          {fileResult && <p style={{ color: '#5eead4', marginTop: '0.5rem', fontSize: '0.9rem' }}>
            ✅ 已上传：<code>{fileResult.event_id}</code>，<Link to="/events" style={{ color: '#5eead4' }}>查看事件 →</Link>
          </p>}
          {fileError && <p style={{ color: '#fecaca', marginTop: '0.5rem', fontSize: '0.9rem' }}>{fileError}</p>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 更新 main.tsx 替换 ingest 路由**

```tsx
import Ingest from './pages/Ingest';
// ...
<Route path="ingest" element={<Ingest />} />
```

- [ ] **Step 3: 构建验证**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

---

### Task 7: 事件列表 + 信息源 + 摘要 + 行动候选页面

**Files:**
- Create: `app/frontend/src/pages/Events.tsx`
- Create: `app/frontend/src/pages/Sources.tsx`
- Create: `app/frontend/src/pages/Digest.tsx`
- Create: `app/frontend/src/pages/Candidates.tsx`
- Create: `app/frontend/src/components/SourceRow.tsx`
- Create: `app/frontend/src/components/CandidateRow.tsx`
- Modify: `app/frontend/src/main.tsx` — 替换所有 placeholder

- [ ] **Step 1: 创建 Events.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import EventRow from '../components/EventRow';
import EmptyState from '../components/EmptyState';

export default function Events() {
  const [events, setEvents] = useState<any[]>([]);
  const [status, setStatus] = useState('');
  const [topic, setTopic] = useState('');

  useEffect(() => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (topic) params.set('topic', topic);
    fetch(`/api/events?${params}`).then(r => r.json()).then(setEvents);
  }, [status, topic]);

  return (
    <div>
      <h2 style={{ color: '#f8fafc', margin: '0 0 1rem' }}>📋 事件列表</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: '1rem' }}>
        <select value={status} onChange={e => setStatus(e.target.value)} style={{
          border: '1px solid rgba(148,163,184,0.22)', borderRadius: 10,
          padding: '0.4rem 0.7rem', background: 'rgba(15,23,42,0.5)', color: '#d8f7f0', fontSize: '0.85rem',
        }}>
          <option value="">全部状态</option>
          <option value="new">新增</option>
          <option value="processing">处理中</option>
          <option value="error">失败</option>
          <option value="digest">已入摘要</option>
        </select>
        <input placeholder="按主题筛选" value={topic} onChange={e => setTopic(e.target.value)} style={{
          border: '1px solid rgba(148,163,184,0.22)', borderRadius: 10,
          padding: '0.4rem 0.7rem', background: 'rgba(15,23,42,0.5)', color: '#d8f7f0', fontSize: '0.85rem',
        }} />
      </div>
      {events.length === 0
        ? <EmptyState icon="📭" title="暂无事件" hint="去「内容摄入」提交抖音链接或上传文件" />
        : <div style={{ display: 'grid', gap: '0.5rem' }}>
            {events.map((e: any) => <EventRow key={e.id} {...e} />)}
          </div>}
    </div>
  );
}
```

- [ ] **Step 2: 创建 SourceRow.tsx**

```tsx
import React from 'react';

const labelMap: Record<string, string> = {
  'Al Jazeera': '半岛电视台', 'BBC Business': 'BBC 商业',
  'BBC Technology': 'BBC 科技', 'BBC Top Stories': 'BBC 头条',
  'BBC World': 'BBC 世界新闻', NPR: 'NPR', 'Reuters World': '路透',
};
const priorityLabels: Record<string, string> = { high: '高', medium: '中', low: '低' };

type Props = { name: string; url: string; type: string; topic: string | null; priority: string; enabled: number; last_checked_at: string | null; last_error: string | null };

export default function SourceRow({ name, url, type, topic, priority, enabled, last_checked_at, last_error }: Props) {
  return (
    <div style={{ border: '1px solid rgba(148,163,184,0.12)', borderRadius: 8, padding: '0.7rem 0.9rem', background: 'rgba(5,15,12,0.3)', display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <div style={{ minWidth: 0 }}>
        <strong style={{ color: '#f8fafc' }}>{labelMap[name] ?? name}</strong>
        <div style={{ color: '#9abeb7', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{url}</div>
        {last_checked_at && <small style={{ color: '#6b8b83' }}>最近采集：{last_checked_at}</small>}
        {last_error && <small style={{ color: '#fecaca', display: 'block' }}>错误：{last_error}</small>}
      </div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <span style={pillStyle}>{type.toUpperCase()}</span>
        {topic && <span style={pillStyle}>{topic}</span>}
        <span style={pillStyle}>{priorityLabels[priority] ?? priority}</span>
        <span style={pillStyle}>{enabled ? '启用' : '停用'}</span>
      </div>
    </div>
  );
}

const pillStyle: React.CSSProperties = {
  border: '1px solid rgba(45,212,191,0.2)',
  borderRadius: 999, padding: '2px 8px',
  color: '#ccfbf1', fontSize: '0.75rem',
};
```

- [ ] **Step 3: 创建 Sources.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import SourceRow from '../components/SourceRow';

export default function Sources() {
  const [sources, setSources] = useState<any[]>([]);
  useEffect(() => { fetch('/api/sources').then(r => r.json()).then(setSources); }, []);
  return (
    <div>
      <h2 style={{ color: '#f8fafc', margin: '0 0 1rem' }}>📡 信息源</h2>
      <div style={{ display: 'grid', gap: '0.5rem' }}>
        {sources.map((s: any) => <SourceRow key={s.id} {...s} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 创建 Digest.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import EmptyState from '../components/EmptyState';

export default function Digest() {
  const [digest, setDigest] = useState<any>(null);
  useEffect(() => { fetch('/api/digest/latest').then(r => r.json()).then(setDigest); }, []);
  if (!digest || !digest.markdown) return <EmptyState icon="📝" title="暂无摘要" hint="点击仪表盘的「生成每日摘要」按钮" />;
  return (
    <div>
      <h2 style={{ color: '#f8fafc', margin: '0 0 1rem' }}>📝 每日摘要</h2>
      <div style={{ display: 'flex', gap: 12, marginBottom: '0.8rem', color: '#ccfbf1', fontSize: '0.9rem' }}>
        <span>日期：{digest.date}</span>
        <span>使用事件：{digest.events_used}</span>
        <span>行动候选：{digest.action_candidates_created}</span>
      </div>
      <pre style={{
        maxHeight: 500, overflow: 'auto', whiteSpace: 'pre-wrap',
        border: '1px solid rgba(148,163,184,0.15)', borderRadius: 12,
        padding: '1rem', background: 'rgba(5,15,12,0.4)',
        color: '#d8f7f0', fontSize: '0.9rem', lineHeight: 1.6,
      }}>{digest.markdown}</pre>
    </div>
  );
}
```

- [ ] **Step 5: 创建 CandidateRow.tsx**

```tsx
import React from 'react';
import StatusPill from './StatusPill';

type Props = {
  id: string; title: string; suggested_action: string; suggested_profile: string | null;
  status: string; event_url: string | null; topic: string | null; task_id: string | null;
  onStatusChange: (id: string, status: string) => void;
  disabled: boolean;
};

export default function CandidateRow({ id, title, suggested_action, suggested_profile, status, event_url, topic, task_id, onStatusChange, disabled }: Props) {
  return (
    <div style={{ border: '1px solid rgba(148,163,184,0.12)', borderRadius: 8, padding: '0.7rem 0.9rem', background: 'rgba(5,15,12,0.3)', display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {event_url
          ? <a href={event_url} target="_blank" rel="noreferrer" style={{ color: '#f8fafc', fontWeight: 600, textDecoration: 'none' }}>{title}</a>
          : <strong style={{ color: '#f8fafc' }}>{title}</strong>}
        <p style={{ margin: '0.3rem 0 0', color: '#9abeb7', fontSize: '0.85rem' }}>{suggested_action}</p>
        <div style={{ display: 'flex', gap: 6, marginTop: '0.4rem', flexWrap: 'wrap' }}>
          <StatusPill status={status} />
          {topic && <span style={{ fontSize: '0.75rem', color: '#6b8b83' }}>{topic}</span>}
          {suggested_profile && <span style={{ fontSize: '0.75rem', color: '#6b8b83' }}>{suggested_profile}</span>}
          {task_id && <span style={{ fontSize: '0.75rem', color: '#6b8b83' }}>任务：{task_id}</span>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <button onClick={() => onStatusChange(id, 'accepted')} disabled={disabled || status === 'accepted'} style={actionBtn}>确认</button>
        <button onClick={() => onStatusChange(id, 'ignored')} disabled={disabled || status === 'ignored'} style={{...actionBtn, borderColor: 'rgba(148,163,184,0.3)', background: 'transparent', color: '#8fb8af'}}>忽略</button>
        <button onClick={() => onStatusChange(id, 'done')} disabled={disabled || status === 'done'} style={{...actionBtn, borderColor: 'rgba(148,163,184,0.3)', background: 'transparent', color: '#8fb8af'}}>已处理</button>
      </div>
    </div>
  );
}

const actionBtn: React.CSSProperties = {
  border: '1px solid rgba(45,212,191,0.35)',
  borderRadius: 999, padding: '0.35rem 0.7rem',
  background: 'rgba(20,184,166,0.12)',
  color: '#ccfbf1', fontWeight: 600, cursor: 'pointer', fontSize: '0.8rem',
};
```

- [ ] **Step 6: 创建 Candidates.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import CandidateRow from '../components/CandidateRow';
import EmptyState from '../components/EmptyState';

export default function Candidates() {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  async function load() {
    const res = await fetch('/api/action-candidates');
    setCandidates(await res.json());
  }

  async function updateStatus(id: string, status: string) {
    setUpdatingId(id);
    await fetch(`/api/action-candidates/${id}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    setUpdatingId(null);
    await load();
  }

  useEffect(() => { load(); }, []);

  return (
    <div>
      <h2 style={{ color: '#f8fafc', margin: '0 0 1rem' }}>✅ 行动候选</h2>
      {candidates.length === 0
        ? <EmptyState icon="✅" title="暂无待审核候选" hint="生成每日摘要后会出现行动候选" />
        : <div style={{ display: 'grid', gap: '0.5rem' }}>
            {candidates.map((c: any) => (
              <CandidateRow key={c.id} {...c}
                onStatusChange={updateStatus}
                disabled={updatingId === c.id}
              />
            ))}
          </div>}
    </div>
  );
}
```

- [ ] **Step 7: 更新 main.tsx — 替换所有 placeholder 路由**

```tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import Dashboard from './pages/Dashboard';
import Ingest from './pages/Ingest';
import Events from './pages/Events';
import Sources from './pages/Sources';
import Digest from './pages/Digest';
import Candidates from './pages/Candidates';
import './style.css';

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />}>
        <Route index element={<Dashboard />} />
        <Route path="ingest" element={<Ingest />} />
        <Route path="events" element={<Events />} />
        <Route path="sources" element={<Sources />} />
        <Route path="digest" element={<Digest />} />
        <Route path="candidates" element={<Candidates />} />
      </Route>
    </Routes>
  </BrowserRouter>
);
```

- [ ] **Step 8: 构建验证**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

预期：构建成功，无 TypeScript 错误

---

### Task 8: 精简 CSS + 最终验证

**Files:**
- Modify: `app/frontend/src/style.css` — 精简，去掉旧页面锚点相关样式
- Modify: `app/frontend/index.html` — 确认入口引用 main.tsx

- [ ] **Step 1: 精简 style.css**

保留全局样式（`:root`、`body`、`a`），去掉不再使用的 `.ki-shell`、`.ki-hero`、`.ki-content` 等旧布局类。内联样式已在组件中处理，CSS 只需保留必要的基础重置。

```css
:root {
  color: #d8f7f0;
  background: #07130f;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(45, 212, 191, 0.18), transparent 34rem),
    linear-gradient(135deg, #07130f 0%, #0b1d18 52%, #0f172a 100%);
}

a { color: inherit; text-decoration: none; }

input:focus, textarea:focus, select:focus {
  outline: none;
  border-color: rgba(45, 212, 191, 0.5) !important;
}

button:disabled { opacity: 0.55; cursor: not-allowed; }
```

- [ ] **Step 2: 构建**

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app/frontend && npm run build 2>&1
```

- [ ] **Step 3: 重启服务验证**

```bash
# Kill old server, restart
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app
/Users/mrh/Documents/hermes-agent/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 9120 &
```

浏览器访问 `http://localhost:9120`：
- 侧边栏 6 个图标导航 ✅
- 点击切换 URL 变化 + 页面内容切换 ✅
- 仪表盘四格指标带图标 ✅
- 内容摄入两个 Tab 切换 ✅
- 事件列表可筛选 ✅
- 所有 API 正常响应 ✅

---

## 验证清单

- [ ] `npm run build` 成功无报错
- [ ] 服务运行在 `http://localhost:9120`
- [ ] 侧边栏图标导航，当前页高亮
- [ ] 点击导航 → URL 变化 → 页面切换（非滚动）
- [ ] 浏览器后退/前进正常
- [ ] 仪表盘指标卡片带 emoji 图标
- [ ] 提交抖音链接 → /ingest → 看到 event_id
- [ ] /events 可看到刚提交的 ingest 事件
- [ ] 所有原有 API（/api/events, /api/sources, /api/digest/latest, /api/action-candidates）正常
