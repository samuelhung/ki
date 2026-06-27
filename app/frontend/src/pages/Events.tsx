import React, { useEffect, useState } from 'react';
import EventRow from '../components/EventRow';
import EmptyState from '../components/EmptyState';
import { X, ExternalLink, Search } from 'lucide-react';
import type { Event } from '../types';
import { formatTimeBeijing } from '../utils';

const PAGE_SIZE = 20;

const topicLabels: Record<string, string> = {
  world: '国际', business: '商业', 'tech-ai': '科技/AI',
  technology: '科技', politics: '政治', science: '科学',
  health: '健康', sports: '体育', entertainment: '娱乐',
};
function formatTopic(t: string) { return topicLabels[t] ?? t; }

export default function Events() {
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState('');
  const [topic, setTopic] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Event | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  function loadEvents(reset: boolean) {
    const newOffset = reset ? 0 : offset;
    if (reset) setOffset(0);
    setLoading(true);
    setError('');
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (topic) params.set('topic', topic);
    if (search) params.set('search', search);
    params.set('offset', String(newOffset));
    params.set('limit', String(PAGE_SIZE));
    fetch(`/api/events?${params}`)
      .then((r) => { if (!r.ok) throw new Error('加载事件失败'); return r.json(); })
      .then((data: Event[]) => {
        if (reset) setEvents(data);
        else setEvents((prev) => [...prev, ...data]);
        setHasMore(data.length === PAGE_SIZE);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadEvents(true); }, [status, topic, search]);
  useEffect(() => { if (offset > 0) loadEvents(false); }, [offset]);

  function loadMore() { setOffset((prev) => prev + PAGE_SIZE); }

  async function showDetail(eventId: string) {
    if (expandedId === eventId) { setExpandedId(null); setDetail(null); return; }
    setExpandedId(eventId);
    setDetailLoading(true);
    try {
      const res = await fetch(`/api/events/${eventId}`);
      if (!res.ok) throw new Error('加载详情失败');
      setDetail(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败');
      setExpandedId(null);
    } finally { setDetailLoading(false); }
  }

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-6 overflow-y-auto custom-scrollbar">
      <div className="max-w-[1080px] mx-auto">
        <h1 className="text-2xl font-bold mb-6">事件列表</h1>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
        )}

        <div className="flex gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-[320px]">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-[#141518] border border-[#2A2B30] text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 transition-colors"
              placeholder="搜索事件内容…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className="px-3 py-2 rounded-lg bg-[#141518] border border-[#2A2B30] text-white focus:outline-none focus:border-purple-500/50 transition-colors"
            value={status} onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="new">新增</option>
            <option value="processing">处理中</option>
            <option value="error">失败</option>
            <option value="digest">已入摘要</option>
          </select>
          <input
            className="px-3 py-2 rounded-lg bg-[#141518] border border-[#2A2B30] text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 transition-colors"
            placeholder="按主题筛选" value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </div>

        {loading && events.length === 0 ? (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
          </div>
        ) : events.length === 0 ? (
          <EmptyState icon="📭" title="暂无事件" hint={search ? '换个搜索词试试' : '去「内容采集」提交抖音链接或上传文件'} />
        ) : (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
            {events.map((e) => (
              <React.Fragment key={e.id}>
                <EventRow {...e} onClick={() => showDetail(e.id)} />
                {expandedId === e.id && (
                  <div className="px-4 py-4 border-b border-[#2A2B30] bg-[#101216]">
                    {detailLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500"></div>
                      </div>
                    ) : detail ? (
                      <div>
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex gap-3 text-xs text-gray-400 flex-wrap">
                            <span>来源：{detail.source_id}</span>
                            {detail.topic && <span>主题：{formatTopic(detail.topic)}</span>}
                            <span>重要性：{detail.importance}/5</span>
                            <span>可行动性：{detail.actionability}/5</span>
                            <span>创建：{formatTimeBeijing(detail.created_at)}</span>
                          </div>
                          <div className="flex gap-2 shrink-0">
                            {detail.url && (
                              <a href={detail.url} target="_blank" rel="noreferrer"
                                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs bg-[#2A2B30] text-gray-400 hover:text-white hover:bg-[#3A3B40] transition-colors">
                                <ExternalLink size={12} /> 原始链接
                              </a>
                            )}
                            <button onClick={() => { setExpandedId(null); setDetail(null); }}
                              className="p-1 rounded hover:bg-[#2A2B30] text-gray-500 hover:text-gray-300 transition-colors">
                              <X size={16} />
                            </button>
                          </div>
                        </div>
                        {detail.title_cn && (
                          <h3 className="text-white font-semibold text-base mb-2">{detail.title_cn}</h3>
                        )}
                        <div className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap max-h-[400px] overflow-y-auto custom-scrollbar bg-[#0B0C10] rounded-lg p-4 border border-[#2A2B30]">
                          {detail.summary_cn || detail.raw_summary || '暂无内容'}
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500">加载详情失败</p>
                    )}
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        )}

        {hasMore && events.length > 0 && !loading && (
          <div className="flex justify-center mt-4">
            <button onClick={loadMore}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-[#141518] border border-[#2A2B30] text-gray-400 hover:bg-[#1A1B20] hover:text-white transition-colors">
              加载更多
            </button>
          </div>
        )}
        {loading && events.length > 0 && (
          <div className="flex items-center justify-center py-4">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500"></div>
          </div>
        )}
      </div>
    </div>
  );
}
