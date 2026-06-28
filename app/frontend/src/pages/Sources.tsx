import React, { useEffect, useState } from 'react';
import SourceRow from '../components/SourceRow';
import ModuleHeroTabs, { WANXIANG_TABS } from '../components/ModuleHeroTabs';
import type { Source } from '../types';
import { apiFetch } from '../api';

export default function Sources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function load() {
    setLoading(true); setError('');
    apiFetch('/api/sources')
      .then((r) => { if (!r.ok) throw new Error('加载信息源失败'); return r.json(); })
      .then(setSources)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  async function handleToggle(id: string) {
    try {
      const res = await apiFetch(`/api/sources/${id}/toggle`, { method: 'PUT' });
      if (!res.ok) throw new Error('切换失败');
      const data = await res.json();
      setSources((prev) => prev.map((s) => (s.id === id ? { ...s, enabled: data.enabled ? 1 : 0 } : s)));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : '操作失败'); }
  }

  async function handleCollect(id: string) {
    try { await apiFetch(`/api/sources/${id}/collect`, { method: 'POST' }); load(); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : '采集失败'); }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8 pb-3">
        <div className="max-w-[1080px] mx-auto">
          <ModuleHeroTabs
            title="万象资料"
            subtitle="每一份内容，都是一粒思想的种子"
            tabs={WANXIANG_TABS.map(tab => tab.to === '/sources' ? { ...tab, count: sources.length } : tab)}
            chips={[
              { label: '信息源', value: sources.length },
              { label: '已启用', value: sources.filter(s => s.enabled).length },
              { label: '暂停', value: sources.filter(s => !s.enabled).length },
              { label: '错误', value: sources.filter(s => s.last_error).length },
            ]}
            actions={[]}
            flowText="输入 → 整理 → 检索 → 复盘"
            note="当前视图：信息源 · 顶部固定，内容独立滚动"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto pt-4">
        {error && <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}<button onClick={load} className="ml-3 underline hover:text-red-300">重试</button></div>}
        {loading ? (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
          </div>
        ) : (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
            {sources.map((s) => <SourceRow key={s.id} {...s} onToggle={() => handleToggle(s.id)} onCollect={() => handleCollect(s.id)} />)}
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
