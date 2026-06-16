import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BookOpen, Loader2, FileCode2, Globe, FileType2, Sparkles, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatTimeBeijing } from '../utils';

interface StudyMaterial {
  id: string;
  subject: string;
  grade: string;
  study_type: string;
  title: string;
  source_type: string;
  raw_content: string;
  child_version: string;
  parent_version: string;
  formats_json: Record<string, string>;
  status: string;
  score: number | null;
  is_correct: number | null;
  mistake_tags: string[];
  created_at: string;
  updated_at: string;
}

type VersionTab = 'child' | 'parent';
type FormatTab = 'md' | 'html' | 'pdf';

const FORMATS: { id: FormatTab; label: string; icon: React.ReactNode }[] = [
  { id: 'md', label: 'MD', icon: <FileCode2 size={14} className="text-blue-400" /> },
  { id: 'html', label: 'HTML', icon: <Globe size={14} className="text-emerald-400" /> },
  { id: 'pdf', label: 'PDF', icon: <FileType2 size={14} className="text-rose-400" /> },
];

export default function StudyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [material, setMaterial] = useState<StudyMaterial | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [version, setVersion] = useState<VersionTab>('parent');
  const [format, setFormat] = useState<FormatTab>('md');
  const [mdContent, setMdContent] = useState('');
  const [generating, setGenerating] = useState(false);

  const loadMaterial = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/study/${id}`);
      if (!r.ok) throw new Error('资料不存在');
      const data = await r.json();
      setMaterial(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadMaterial(); }, [id]);

  // Load MD content when switching to MD format
  useEffect(() => {
    if (!material || format !== 'md') { setMdContent(''); return; }
    const text = version === 'child' ? material.child_version : material.parent_version;
    setMdContent(text || '');
  }, [material, version, format]);

  const handleGenerate = async () => {
    if (!id) return;
    setGenerating(true);
    try {
      const r = await fetch(`/api/study/${id}/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      if (!r.ok) throw new Error('生成失败');
      await loadMaterial();
    } catch (e: any) {
      setError(e.message || '生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const getFormatUrl = () => {
    if (!material || !id) return '';
    const paths = material.formats_json || {};
    const key = format === 'md' ? 'md' : format === 'html' ? 'html' : 'pdf';
    if (paths[key]) return `/api/study/${id}/file/${format}`;
    return '';
  };

  if (loading) {
    return <div className="flex-1 bg-[#0B0C10] flex items-center justify-center"><Loader2 size={24} className="animate-spin text-gray-500" /></div>;
  }

  if (error || !material) {
    return (
      <div className="flex-1 bg-[#0B0C10] flex items-center justify-center">
        <div className="text-center"><p className="text-red-400 text-sm">{error || '资料不存在'}</p>
          <button onClick={() => navigate('/study')} className="mt-4 text-xs text-gray-500 hover:text-gray-300">返回辅导中心</button>
        </div>
      </div>
    );
  }

  const isReady = material.status === 'ready' || material.status === 'reviewed';

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* 头部 */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-6xl mx-auto">
          {/* 面包屑 */}
          <button onClick={() => navigate('/study')} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 mb-3 transition-colors">
            <ArrowLeft size={14} /> 辅导中心
          </button>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#1A1B20] border border-[#2A2B30] flex items-center justify-center text-lg font-medium shrink-0">
                  {material.subject === '语文' ? '语' : material.subject === '数学' ? '数' : 'E'}
                </div>
                <div className="min-w-0">
                  <h1 className="text-xl font-bold truncate">{material.title}</h1>
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-500">
                    <span className={`px-1.5 py-0.5 rounded ${
                      material.subject === '语文' ? 'text-blue-400 bg-blue-500/10' :
                      material.subject === '数学' ? 'text-amber-400 bg-amber-500/10' :
                      'text-emerald-400 bg-emerald-500/10'
                    }`}>{material.subject}</span>
                    <span>{material.study_type}</span>
                    {material.grade && <span>{material.grade}</span>}
                    <span>{formatTimeBeijing(material.created_at)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center gap-2 flex-wrap">
              {!isReady && (
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                  <span className="hidden sm:inline">生成讲稿</span>
                </button>
              )}
              {isReady && (
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  <span className="hidden sm:inline">重新生成</span>
                </button>
              )}
            </div>
          </div>

          {/* Version tab */}
          {isReady && (
            <div className="border-b border-[#2A2B30] mb-3">
              <div className="flex gap-6">
                {[
                  { id: 'child' as VersionTab, label: '👦 孩子版' },
                  { id: 'parent' as VersionTab, label: '👨‍🏫 家长版' },
                ].map(v => (
                  <button
                    key={v.id}
                    onClick={() => setVersion(v.id)}
                    className={`pb-3 text-xs font-medium transition-colors relative ${
                      version === v.id ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {v.label}
                    {version === v.id && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-6xl mx-auto">
          {!isReady ? (
            <div className="text-center text-gray-600 py-16">
              <Sparkles size={48} className="mx-auto mb-4 opacity-40" />
              <p className="text-sm">尚未生成讲题稿</p>
              <p className="text-xs mt-1 text-gray-700">点击上方「生成讲稿」开始 AI 生成</p>
            </div>
          ) : (
            <>
              {/* Format switch */}
              <div className="flex gap-1 mb-4">
                {FORMATS.filter(f => {
                  if (f.id === 'md') return true;
                  const paths = material.formats_json || {};
                  return !!paths[f.id] || !!paths[f.id === 'html' ? 'html' : 'pdf'];
                }).map(f => (
                  <button
                    key={f.id}
                    onClick={() => setFormat(f.id)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                      format === f.id ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {f.icon}
                    {f.label}
                  </button>
                ))}
              </div>

              {/* MD View */}
              {format === 'md' && (
                <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-6 prose prose-invert prose-sm max-w-none">
                  {mdContent ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{mdContent}</ReactMarkdown>
                  ) : (
                    <div className="text-gray-500 text-sm py-8 text-center">加载中...</div>
                  )}
                </div>
              )}

              {/* HTML / PDF iframe */}
              {(format === 'html' || format === 'pdf') && (
                <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden" style={{ height: 'calc(100vh - 280px)' }}>
                  <iframe src={getFormatUrl()} className="w-full h-full border-0" title={`${format} Preview`} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
