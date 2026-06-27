import React, { useEffect, useState } from 'react';
import SourceRow from '../components/SourceRow';
import type { Source } from '../types';

export default function Sources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function load() {
    setLoading(true); setError('');
    fetch('/api/sources')
      .then((r) => { if (!r.ok) throw new Error('加载信息源失败'); return r.json(); })
      .then(setSources)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  async function handleToggle(id: string) {
    try {
      const res = await fetch(`/api/sources/${id}/toggle`, { method: 'PUT' });
      if (!res.ok) throw new Error('切换失败');
      const data = await res.json();
      setSources((prev) => prev.map((s) => (s.id === id ? { ...s, enabled: data.enabled ? 1 : 0 } : s)));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : '操作失败'); }
  }

  async function handleCollect(id: string) {
    try { await fetch(`/api/sources/${id}/collect`, { method: 'POST' }); load(); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : '采集失败'); }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-6 overflow-y-auto custom-scrollbar">
      <div className="max-w-[1080px] mx-auto">
        <h1 className="text-2xl font-bold mb-6">信息源</h1>
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
  );
}
