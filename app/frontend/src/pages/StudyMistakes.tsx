import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import { ArrowLeft, Loader2, AlertTriangle } from 'lucide-react';
import { formatTimeBeijing } from '../utils';

interface MistakeItem {
  id: string;
  subject: string;
  grade: string;
  study_type: string;
  title: string;
  score: number | null;
  mistake_tags: string[];
  created_at: string;
}

const SUBJECTS = ['全部', '语文', '数学', '英语'];

export default function StudyMistakes() {
  const navigate = useNavigate();
  const { navigateWithCurtain } = useCurtain();
  const [items, setItems] = useState<MistakeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [subject, setSubject] = useState('全部');
  const [error, setError] = useState('');

  // Stats
  const [allTags, setAllTags] = useState<{ tag: string; count: number }[]>([]);

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (subject !== '全部') params.set('subject', subject);
      const r = await fetch(`/api/study/mistakes/list?${params.toString()}`);
      if (!r.ok) throw new Error('加载失败');
      const data = await r.json();
      setItems(data.items || []);

      // Build tag cloud
      const tagCounts: Record<string, number> = {};
      (data.items || []).forEach((item: MistakeItem) => {
        (item.mistake_tags || []).forEach((tag: string) => {
          tagCounts[tag] = (tagCounts[tag] || 0) + 1;
        });
      });
      setAllTags(Object.entries(tagCounts).map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count));
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [subject]);

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* 吸顶头部 */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">
          <button onClick={() => navigate('/study')} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 mb-3 transition-colors">
            <ArrowLeft size={14} /> 辅导中心
          </button>
          <div className="flex items-center gap-3 mb-4">
            <AlertTriangle size={40} className="text-red-400 shrink-0" />
            <div>
              <h1 className="text-2xl font-bold">错题本</h1>
              <p className="text-gray-400 text-sm mt-0.5">错题归类与薄弱点分析</p>
            </div>
          </div>

          {error && <div className="text-red-400 text-xs mb-3 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</div>}

          {/* Tab 栏 */}
          <div className="border-b border-[#2A2B30]">
            <div className="flex gap-6">
              {SUBJECTS.map(s => (
                <button
                  key={s}
                  onClick={() => setSubject(s)}
                  className={`pb-3 text-xs font-medium transition-colors relative ${
                    subject === s ? 'text-red-400' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {s}
                  {subject === s && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-red-500" />}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto pt-4">
          {loading ? (
            <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-gray-500" /></div>
          ) : (
            <>
              {/* 薄弱点标签云 */}
              {allTags.length > 0 && (
                <div className="mb-6 bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
                  <h3 className="text-xs font-medium text-gray-400 mb-3">薄弱点分布</h3>
                  <div className="flex flex-wrap gap-2">
                    {allTags.map(({ tag, count }) => (
                      <span key={tag} className="text-[10px] px-2 py-1 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                        {tag} ×{count}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {items.length === 0 ? (
                <div className="text-center text-gray-600 py-16">
                  <AlertTriangle size={48} className="mx-auto mb-4 opacity-40" />
                  <p className="text-sm">暂无错题记录</p>
                </div>
              ) : (
                <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[#2A2B30] text-gray-500">
                        <th className="text-left py-3 px-4 font-medium">标题</th>
                        <th className="text-left py-3 px-4 font-medium hidden sm:table-cell">学科</th>
                        <th className="text-left py-3 px-4 font-medium hidden md:table-cell">题型</th>
                        <th className="text-left py-3 px-4 font-medium hidden md:table-cell">错因标签</th>
                        <th className="text-right py-3 px-4 font-medium hidden lg:table-cell w-36">时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map(item => (
                        <tr
                          key={item.id}
                          onClick={() => navigateWithCurtain(`/study/${item.id}`)}
                          className="border-b border-[#2A2B30] last:border-b-0 hover:bg-[#1A1B20] cursor-pointer transition-colors"
                        >
                          <td className="py-3 px-4">
                            <span className="text-gray-200 truncate block max-w-[300px]">{item.title}</span>
                          </td>
                          <td className="py-3 px-4 hidden sm:table-cell">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              item.subject === '语文' ? 'text-blue-400 bg-blue-500/10' :
                              item.subject === '数学' ? 'text-amber-400 bg-amber-500/10' :
                              'text-emerald-400 bg-emerald-500/10'
                            }`}>{item.subject}</span>
                          </td>
                          <td className="py-3 px-4 text-gray-400 hidden md:table-cell">{item.study_type}</td>
                          <td className="py-3 px-4 hidden md:table-cell">
                            <div className="flex flex-wrap gap-1">
                              {(item.mistake_tags || []).slice(0, 3).map(tag => (
                                <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">{tag}</span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 px-4 text-right text-gray-600 hidden lg:table-cell">{formatTimeBeijing(item.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
