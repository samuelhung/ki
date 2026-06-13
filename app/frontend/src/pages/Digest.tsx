import React, { useEffect, useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import EmptyState from '../components/EmptyState';
import { RefreshCw, ChevronDown, ChevronRight, Lightbulb, FileText } from 'lucide-react';
import type { Digest } from '../types';

interface DigestSection {
  type: 'title' | 'headline' | 'overview' | 'topic' | 'qa' | 'expandable';
  heading: string;
  content: string;
}

interface QAPair {
  question: string;
  answer: string;
}

/** Parse markdown into typed sections by ## headings */
function parseSections(md: string): DigestSection[] {
  const sections: DigestSection[] = [];
  // Split on ## (level-2 markdown headings), including the heading text
  const parts = md.split(/^## /m);

  // Part 0 is everything before the first ## (title + headline)
  if (parts[0].trim()) {
    sections.push({ type: 'title', heading: '', content: parts[0].trim() });
  }

  for (let i = 1; i < parts.length; i++) {
    const block = parts[i];
    const nl = block.indexOf('\n');
    const heading = nl > 0 ? block.substring(0, nl).trim() : block.trim();
    const content = nl > 0 ? block.substring(nl + 1).trim() : '';

    let type: DigestSection['type'] = 'topic';
    if (heading.includes('今日要闻')) type = 'headline';
    else if (heading.includes('事件总览')) type = 'overview';
    else if (heading.includes('关键问答')) type = 'qa';
    else if (heading.includes('可拓展问题')) type = 'expandable';

    sections.push({ type, heading, content });
  }

  return sections;
}

/** Parse QA section content into Q&A pairs */
function parseQAPairs(content: string): QAPair[] {
  const pairs: QAPair[] = [];
  // Split by ### Q: or **Q:** patterns
  const qBlocks = content.split(/^###\s*Q:\s*/m).filter(Boolean);

  for (const block of qBlocks) {
    const aIdx = block.indexOf('\nA: ');
    const question = aIdx > 0 ? block.substring(0, aIdx).trim() : block.trim();
    const answer = aIdx > 0
      ? block.substring(aIdx + 4).trim()
      : '';
    if (question) {
      pairs.push({ question, answer });
    }
  }

  return pairs;
}

/** Parse expandable questions from markdown list */
function parseExpandableQuestions(content: string): string[] {
  return content
    .split('\n')
    .filter(line => line.trim().startsWith('- ') || line.trim().startsWith('* '))
    .map(line => line.replace(/^[-*]\s+/, '').trim())
    .filter(Boolean);
}

/** QA Card: collapsible question + answer */
function QACard({ qa, defaultOpen = false }: { qa: QAPair; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border border-[#2A2B30] rounded-xl overflow-hidden bg-[#0B0C10] hover:border-purple-500/30 transition-colors">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-[#141518] transition-colors"
      >
        <span className={`transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>
          <ChevronRight size={16} className="text-purple-400 shrink-0" />
        </span>
        <span className="text-sm font-medium text-gray-200 flex-1">{qa.question}</span>
      </button>
      {open && (
        <div className="px-5 pb-4 pt-0 border-t border-[#2A2B30] mx-5">
          <p className="text-sm text-gray-300 leading-relaxed pt-4">{qa.answer}</p>
        </div>
      )}
    </div>
  );
}

/** Expandable question card */
function ExpandableCard({ question }: { question: string }) {
  return (
    <div className="border border-[#2A2B30] rounded-xl p-4 bg-[#0B0C10] hover:border-purple-500/30 transition-colors flex items-start gap-3 group">
      <Lightbulb size={16} className="text-amber-400 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-300 leading-relaxed">{question}</p>
      </div>
    </div>
  );
}

export default function DigestPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [generating, setGenerating] = useState(false);
  const [expandedQAs, setExpandedQAs] = useState<Set<number>>(new Set());

  function load() {
    setLoading(true); setError('');
    fetch('/api/digest/latest')
      .then((r) => { if (!r.ok) throw new Error('加载摘要失败'); return r.json(); })
      .then(setDigest)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  async function handleRegenerate() {
    setGenerating(true);
    try {
      const res = await fetch('/api/digest/generate', { method: 'POST' });
      if (!res.ok) throw new Error('摘要生成失败');
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '摘要生成失败');
    } finally {
      setGenerating(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Parse markdown into sections
  const sections = useMemo(() => {
    if (!digest?.markdown) return [];
    return parseSections(digest.markdown);
  }, [digest?.markdown]);

  // Pre-parse QA pairs and expandable questions
  const qaSection = useMemo(() => {
    const s = sections.find(s => s.type === 'qa');
    return s ? parseQAPairs(s.content) : [];
  }, [sections]);

  const expandableQuestions = useMemo(() => {
    const s = sections.find(s => s.type === 'expandable');
    return s ? parseExpandableQuestions(s.content) : [];
  }, [sections]);

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-3">
              <FileText size={40} className="text-purple-400 shrink-0" />
              <div>
                <h1 className="text-2xl font-bold">每日摘要</h1>
                {digest && (
                  <p className="text-gray-400 text-sm mt-0.5">
                    {digest.date} · {digest.events_used} 条记录
                  </p>
                )}
              </div>
            </div>
          </div>
          <button onClick={handleRegenerate} disabled={generating}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
            <RefreshCw size={14} className={generating ? 'animate-spin' : ''} />
            {generating ? '生成中...' : '重新生成'}
          </button>
        </div>

          {/* Error */}
          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
              <button onClick={load} className="ml-3 underline hover:text-red-300">重试</button>
            </div>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-6xl mx-auto pt-4">

        {/* Loading */}
        {loading ? (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
          </div>
        ) : !digest || !digest.markdown ? (
          <EmptyState icon="📝" title="暂无摘要" hint="点击「重新生成」生成今日摘要" />
        ) : (
          <div className="space-y-5">
            {/* Title area: main heading */}
            {sections.find(s => s.type === 'title') && (
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <div className="prose-sm text-gray-300 [&_h1]:text-xl [&_h1]:font-bold [&_h1]:text-white [&_h1]:mb-3 [&_p]:text-sm [&_p]:leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {sections.find(s => s.type === 'title')!.content}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Headline section */}
            {sections.find(s => s.type === 'headline') && (() => {
              const s = sections.find(s => s.type === 'headline')!;
              return (
                <div className="bg-gradient-to-r from-purple-500/10 to-transparent border border-purple-500/20 rounded-xl p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">📰</span>
                    <h2 className="text-sm font-semibold text-purple-400">今日要闻</h2>
                  </div>
                  <div className="text-sm text-gray-300 leading-relaxed [&_p]:mb-2">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {s.content}
                    </ReactMarkdown>
                  </div>
                </div>
              );
            })()}

            {/* Overview section */}
            {sections.find(s => s.type === 'overview') && (() => {
              const s = sections.find(s => s.type === 'overview')!;
              return (
                <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">📊</span>
                    <h2 className="text-sm font-semibold text-gray-200">事件总览</h2>
                  </div>
                  <div className="text-sm text-gray-400 leading-relaxed">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {s.content}
                    </ReactMarkdown>
                  </div>
                </div>
              );
            })()}

            {/* Topic sections (non-QA, non-expandable, non-title, non-headline, non-overview) */}
            {sections.filter(s => s.type === 'topic').map((s, i) => (
              <div key={i} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-gray-200 mb-3">{s.heading}</h2>
                <div className="text-sm text-gray-300 leading-relaxed prose-sm
                  [&_h3]:text-xs [&_h3]:font-semibold [&_h3]:text-purple-400 [&_h3]:mt-5 [&_h3]:mb-2
                  [&_p]:mb-2 [&_p]:text-gray-400
                  [&_ul]:space-y-1.5 [&_ol]:space-y-1.5
                  [&_a]:text-purple-400 [&_a]:underline [&_a]:underline-offset-2
                  [&_strong]:text-gray-200 [&_strong]:font-semibold
                ">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.content}</ReactMarkdown>
                </div>
              </div>
            ))}

            {/* QA Section */}
            {qaSection.length > 0 && (
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">❓</span>
                  <h2 className="text-sm font-semibold text-gray-200">今日关键问答</h2>
                  <span className="text-xs text-gray-500 ml-auto">{qaSection.length} 组问答</span>
                </div>
                <div className="space-y-2.5">
                  {qaSection.map((qa, i) => (
                    <QACard key={i} qa={qa} defaultOpen={i === 0} />
                  ))}
                </div>
              </div>
            )}

            {/* Expandable Questions */}
            {expandableQuestions.length > 0 && (
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">🔍</span>
                  <h2 className="text-sm font-semibold text-gray-200">可拓展问题</h2>
                  <span className="text-xs text-gray-500 ml-auto">{expandableQuestions.length} 个方向</span>
                </div>
                <div className="space-y-2.5">
                  {expandableQuestions.map((q, i) => (
                    <ExpandableCard key={i} question={q} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
    </div>
  );
}
