import React, { useEffect, useState } from 'react';
import { Trash2, X, ChevronLeft, ChevronRight, Lightbulb, Search, Maximize2, Globe, Coins, Brain, Telescope } from 'lucide-react';
import EmptyState from '../components/EmptyState';
import Checkbox from '../components/Checkbox';
import MetricCard from '../components/MetricCard';
import { formatTimeBeijing } from '../utils';
import BrainstormDetailPanel from './panels/BrainstormDetailPanel';

interface BrainstormQuestion {
  id: string;
  event_id: string;
  question: string;
  status: string;
  topic: string;
  created_at: string;
  title: string | null;
  title_cn: string | null;
  source_id: string;
  url: string | null;
  answered_event_ids: string | null;
}

interface EventItem {
  id: string;
  title: string;
  title_cn: string | null;
  source_id: string;
  url: string;
  status: string;
  created_at: string;
}

const PAGE_SIZE = 20;

const TOPICS = [
  { key: '格局', label: '格局', sub: '地缘政治·大国博弈·国际关系', icon: Globe, color: 'text-blue-400' },
  { key: '财富', label: '财富', sub: '经济金融·商业洞察·投资理财', icon: Coins, color: 'text-amber-400' },
  { key: '认知', label: '认知', sub: '思维模型·方法论·底层逻辑', icon: Brain, color: 'text-purple-400' },
  { key: '前瞻', label: '前瞻', sub: '科技趋势·未来预判·前沿动态', icon: Telescope, color: 'text-emerald-400' },
] as const;

function topicBadgeClass(topic: string): string {
  switch (topic) {
    case '格局': return 'bg-blue-500/15 text-blue-400';
    case '财富': return 'bg-amber-500/15 text-amber-400';
    case '认知': return 'bg-purple-500/15 text-purple-400';
    case '前瞻': return 'bg-emerald-500/15 text-emerald-400';
    default: return 'bg-gray-500/15 text-gray-400';
  }
}

export default function Brainstorm() {
  const [questions, setQuestions] = useState<BrainstormQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<string>('格局');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<BrainstormQuestion | null>(null);
  const [showSearch, setShowSearch] = useState(false);

  // Create modal state
  const [showCreate, setShowCreate] = useState(false);
  const [newQuestion, setNewQuestion] = useState('');
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState('');
  const [topicCounts, setTopicCounts] = useState<Record<string, number>>({});

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newQuestion.trim()) return;
    setCreateLoading(true); setCreateError('');
    try {
      const r = await fetch('/api/brainstorm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: newQuestion.trim() }),
      });
      if (r.ok) {
        setShowCreate(false);
        setNewQuestion('');
        await load();
      } else {
        const d = await r.json();
        setCreateError(d.detail || '创建失败');
      }
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : '网络错误');
    }
    setCreateLoading(false);
  }

  async function load() {
    setLoading(true); setError('');
    const params = new URLSearchParams();
    params.set('topic', tab);
    const qs = params.toString();
    fetch(`/api/brainstorm${qs ? '?' + qs : ''}`)
      .then((r) => { if (!r.ok) throw new Error('加载失败'); return r.json(); })
      .then((data) => setQuestions(data.questions || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  function closeDetail() {
    setSelected(null);
  }

  async function remove(id: string) {
    if (!confirm('确认删除这条问题？')) return;
    try {
      await fetch(`/api/brainstorm/${id}`, { method: 'DELETE' });
      if (selected?.id === id) closeDetail();
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function batchDelete() {
    if (selectedIds.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 条问题吗？`)) return;
    try {
      await fetch('/api/brainstorm/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_ids: Array.from(selectedIds) }),
      });
      setSelectedIds(new Set());
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '删除失败');
    }
  }

  function toggleSelectQ(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  useEffect(() => { load(); setPage(1); setSelectedIds(new Set()); }, [tab, search]);
  useEffect(() => { loadTopicCounts(); }, []);

  async function loadTopicCounts() {
    try {
      const r = await fetch('/api/brainstorm/topic-counts');
      const d = await r.json();
      setTopicCounts(d);
    } catch (e: any) { console.error('加载话题计数失败', e); }
  }

  // Client-side search filter
  function filteredQuestions(): BrainstormQuestion[] {
    if (!search.trim()) return questions;
    const s = search.toLowerCase();
    return questions.filter(q => q.question.toLowerCase().includes(s));
  }

  const allCount = questions.length;

  // Pagination
  const filtered = filteredQuestions();
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  return (
    <>
      <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-6 overflow-y-auto custom-scrollbar">
        <div className="max-w-6xl mx-auto">

          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <div className="flex items-center gap-3">
                <Lightbulb size={40} className="text-purple-400 shrink-0" />
                <div>
                  <h1 className="text-2xl font-bold">头脑风暴</h1>
                  <p className="text-sm text-gray-400 mt-0.5">好的问题，比答案更接近真相</p>
                </div>
              </div>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="hidden md:inline-flex px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors"
            >
              + 新建问题
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
              <button onClick={load} className="ml-3 underline hover:text-red-300">重试</button>
            </div>
          )}

          {/* Tabs — Ingest style */}
          <div className="border-b border-[#2A2B30] mb-6 hidden md:block">
            <div className="flex gap-6 overflow-x-auto">
              {TOPICS.map(t => (
                <button key={t.key} onClick={() => { setTab(t.key); setPage(1); }}
                  className={`pb-3 text-sm font-medium transition-colors relative whitespace-nowrap flex flex-col items-center ${tab === t.key ? 'text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                  <div className="flex items-center"><t.icon size={18} className={`${t.color} mr-1.5`} />{t.label}</div>
                  {t.sub && <div className="text-[10px] text-gray-500 mt-0.5 font-normal">{t.sub}</div>}
                  {tab === t.key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500" />}
                </button>
              ))}
            </div>
          </div>

          {/* 手机 tab 下拉 */}
          <select
            className="md:hidden w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white focus:outline-none focus:border-purple-500/50 mb-4"
            value={tab}
            onChange={e => { setTab(e.target.value); setPage(1); }}
          >
            {TOPICS.map(t => (
              <option key={t.key} value={t.key}>
                {t.label} · {t.sub}
              </option>
            ))}
          </select>

          {/* Table */}
          {loading ? (
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
            </div>
          ) : questions.length === 0 ? (
            <EmptyState icon="💡" title="暂无头脑风暴问题" hint="点击上方「+ 新建问题」按钮手动添加灵感" />
          ) : (
            <>
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
                {/* Table header */}
                <div className="hidden md:grid grid-cols-12 gap-4 px-5 py-3 text-sm text-gray-500 border-b border-[#2A2B30] items-center">
                  <div className="col-span-1"></div>
                  <div className="col-span-5">问题</div>
                  <div className="col-span-1 text-center">分类</div>
                  <div className="col-span-2 text-center">关联文档</div>
                  <div className="col-span-2 text-center">提交时间</div>
                  <div className="col-span-1 text-center">操作</div>
                </div>

                {paged.length === 0 ? (
                  <div className="px-5 py-12 text-center text-gray-500 text-sm">
                    {search ? '没有匹配的结果' : '暂无数据'}
                  </div>
                ) : (
                  paged.map((q) => (
                    <React.Fragment key={q.id}>
                    {/* 桌面行 */}
                    <div
                      onClick={() => { if (window.getSelection()?.toString()) return; toggleSelectQ(q.id); }}
                      className="hidden md:grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-[#1A1B20] transition-colors cursor-pointer border-b border-[#2A2B30] last:border-b-0">
                      <div className="col-span-1 flex justify-center" onClick={e => e.stopPropagation()}>
                        <Checkbox checked={selectedIds.has(q.id)} onChange={() => toggleSelectQ(q.id)} />
                      </div>
                      <div className="col-span-5 min-w-0">
                        <div className="text-sm leading-relaxed truncate text-gray-200">{q.question}</div>
                      </div>
                      <div className="col-span-1 text-center">
                        {q.topic ? (
                          <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${topicBadgeClass(q.topic)}`}>{q.topic}</span>
                        ) : (
                          <span className="text-gray-600 text-xs">—</span>
                        )}
                      </div>
                      <div className="col-span-2 text-center">
                        {(() => {
                          let count = 0;
                          try { count = JSON.parse(q.answered_event_ids || '[]').length; } catch (e) { console.error('解析关联文档ID失败', e); }
                          return (
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${count > 0 ? 'bg-purple-500/15 text-purple-400' : 'text-gray-600'}`}>
                              {count > 0 ? `${count} 篇` : '—'}
                            </span>
                          );
                        })()}
                      </div>
                      <div className="col-span-2 text-center text-xs text-gray-500">
                        {formatTimeBeijing(q.created_at)}
                      </div>
                      <div className="col-span-1 flex justify-center gap-0.5" onClick={e => e.stopPropagation()}>
                        <button onClick={() => setSelected(q)}
                          className="p-1.5 rounded text-gray-500 hover:text-purple-400 hover:bg-[#2A2B30] transition-colors"
                          title="查看详情">
                          <Maximize2 size={15} />
                        </button>
                        <button onClick={() => remove(q.id)}
                          className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-[#2A2B30] transition-colors"
                          title="删除">
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                    {/* 手机行 — 紧凑列表 */}
                    <div
                      className="md:hidden flex items-center gap-3 px-4 py-3 hover:bg-[#1A1B20] border-b border-[#2A2B30] last:border-b-0 cursor-pointer"
                      onClick={() => setSelected(q)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-200 truncate">{q.question}</div>
                        <div className="flex items-center gap-2 mt-1">
                          {q.topic && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${topicBadgeClass(q.topic)}`}>{q.topic}</span>
                          )}
                        </div>
                      </div>
                      <ChevronRight size={14} className="text-gray-600 shrink-0" />
                    </div>
                    </React.Fragment>
                  ))
                )}
              </div>

              {/* Bottom bar */}
              <div className="flex items-center justify-between mt-4 text-sm">
                <div className="relative w-52 hidden md:block">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input type="text" placeholder="搜索问题..."
                    value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                    className="w-full pl-8 pr-3 py-1.5 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50" />
                </div>
                <button className="md:hidden p-2 rounded text-gray-400" onClick={() => setShowSearch(!showSearch)}>
                  <Search size={16} />
                </button>
                <div>
                  {selectedIds.size > 0 && (
                    <button onClick={batchDelete}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-colors">
                      删除选中 ({selectedIds.size})
                    </button>
                  )}
                </div>
                {totalPages > 1 ? (
                  <div className="flex items-center gap-1 text-gray-400">
                    <span className="text-xs mr-1">共 {topicCounts[tab] ?? '...'} 条 · 第 {safePage}/{totalPages} 页</span>
                    <button onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={safePage <= 1}
                      className="p-1.5 rounded-lg hover:bg-[#2A2B30] hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                      <ChevronLeft size={16} />
                    </button>
                    <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={safePage >= totalPages}
                      className="p-1.5 rounded-lg hover:bg-[#2A2B30] hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                      <ChevronRight size={16} />
                    </button>
                  </div>
                ) : (
                  <span className="text-xs text-gray-500">共 {topicCounts[tab] ?? '...'} 条</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 手机搜索展开 */}
      {showSearch && (
        <div className="md:hidden mt-3">
          <input
            autoFocus
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="搜索问题..."
            className="w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
          />
        </div>
      )}

      {/* 手机端 FAB */}
      <button
        onClick={() => setShowCreate(true)}
        className="md:hidden fixed bottom-20 right-4 z-30 w-12 h-12 rounded-full bg-amber-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
      </button>

      {/* 底部留白 */}
      <div className="md:hidden h-16" />

      {/* Detail Panel */}
      {selected && (
        <BrainstormDetailPanel question={selected} onClose={closeDetail} />
      )}

      {/* Create Question Modal */}
      {showCreate && (
        <>
          <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl w-full max-w-lg shadow-2xl" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30]">
                <h3 className="text-white font-semibold">新建问题</h3>
                <button onClick={() => setShowCreate(false)}
                  className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30]">
                  <X size={18} />
                </button>
              </div>
              <form onSubmit={handleCreate} className="px-5 py-4 space-y-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5">问题内容</label>
                  <textarea
                    value={newQuestion}
                    onChange={e => setNewQuestion(e.target.value)}
                    placeholder="输入你想探索的问题..."
                    rows={3}
                    className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50 resize-none"
                  />
                </div>
                {createError && (
                  <div className="text-xs text-red-400">{createError}</div>
                )}
                <div className="flex justify-end gap-2 pt-2">
                  <button type="button" onClick={() => setShowCreate(false)}
                    className="px-4 py-2 rounded-lg text-sm bg-[#2A2B30] text-gray-300 hover:bg-[#3A3B40] transition-colors">
                    取消
                  </button>
                  <button type="submit" disabled={createLoading || !newQuestion.trim()}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                    {createLoading ? '分类中...' : '创建'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </>
      )}
    </>
  );
}