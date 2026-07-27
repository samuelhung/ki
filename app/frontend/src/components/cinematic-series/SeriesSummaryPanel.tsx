import React, { useMemo } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import type { SeriesDetailData } from '../../pages/SeriesDetail';
import { renderLineWithRefs, summaryToHtml } from './seriesDetailFormat';

export type SeriesDetailTab = 'overview' | 'paper' | 'content';

interface SeriesSummaryPanelProps {
  series: SeriesDetailData;
  embedded: boolean;
  tab: SeriesDetailTab;
  memberCount: number;
  introGenerating: boolean;
  summaryGenerating: boolean;
  paperGenerating: boolean;
  onSelectTab: (tab: SeriesDetailTab) => void;
  onGenerateIntro: () => void;
  onGenerateSummary: () => void;
  onGeneratePaper: () => void;
  onReferenceClick: (reference: number) => void;
}

export default function SeriesSummaryPanel({
  series, embedded, tab, memberCount, introGenerating, summaryGenerating, paperGenerating,
  onSelectTab, onGenerateIntro, onGenerateSummary, onGeneratePaper, onReferenceClick,
}: SeriesSummaryPanelProps) {
  const summaryHtml = useMemo(() => series.summary ? summaryToHtml(series.summary) : '', [series.summary]);
  const paperHtml = useMemo(() => series.paper ? summaryToHtml(series.paper, 'paper') : '', [series.paper]);
  const anyGenerating = introGenerating || summaryGenerating || paperGenerating;
  const handleGenerateIntro = onGenerateIntro;
  const handleGenerateSummary = onGenerateSummary;
  const handleGeneratePaper = onGeneratePaper;
  const handleRefClick = onReferenceClick;

  return <>
    {(embedded || series.intro) && (
      <div className="series-intro-section mb-6 bg-gradient-to-r from-purple-500/5 to-transparent border border-purple-500/10 rounded-xl p-5">
        <div className="series-context-heading flex items-center gap-2 mb-3">
          <Sparkles size={14} className="text-purple-400" />
          <span className="text-xs font-medium text-purple-400">专题导言</span>
          {embedded && (
            <button className="series-context-action series-intro-action" onClick={handleGenerateIntro} disabled={anyGenerating || memberCount < 2}>
              {introGenerating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              {series.intro ? '重新生成' : '生成导言'}
            </button>
          )}
        </div>
        {series.intro ? (
          <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-line">
            {series.intro.split('\n').map((line, index) => (
              <React.Fragment key={index}>
                {index > 0 && <br />}
                {renderLineWithRefs(line, handleRefClick)}
              </React.Fragment>
            ))}
          </p>
        ) : <p className="series-context-empty">尚未生成专题导言。</p>}
      </div>
    )}

    <div className="flex items-center justify-between mb-6 border-b border-[#2A2B30]">
      <div className="flex gap-4">
        <button onClick={() => onSelectTab('overview')} className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'overview' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>结构化速览</button>
        <button onClick={() => onSelectTab('paper')} className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'paper' ? 'text-sky-400 border-sky-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>深度分析</button>
        <button onClick={() => onSelectTab('content')} className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'content' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>专题内容</button>
      </div>
    </div>

    {tab === 'overview' && <div className="space-y-6">
      {series.summary ? <div>
        <div className="series-context-heading flex items-center gap-2 mb-3">
          <span className="text-[11px] text-emerald-400 font-medium">结构化速览</span>
          {embedded && <button className="series-context-action series-summary-action" onClick={handleGenerateSummary} disabled={anyGenerating || memberCount < 2}>
            {summaryGenerating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}重新生成
          </button>}
        </div>
        <div className="text-xs ref-container" onClick={(event) => {
          const element = (event.target as HTMLElement).closest('.ref-link') as HTMLElement | null;
          const reference = parseInt(element?.dataset.ref || '0');
          if (reference > 0) handleRefClick(reference);
        }} dangerouslySetInnerHTML={{ __html: summaryHtml }} />
      </div> : <div className="series-context-empty-state py-12 text-center">
        <p className="text-xs text-gray-500">尚未生成结构化速览</p>
        {embedded && <button className="series-context-action series-summary-action" onClick={handleGenerateSummary} disabled={anyGenerating || memberCount < 2}><Sparkles size={12} />生成结构化速览</button>}
      </div>}
      {!embedded && !series.intro && !series.summary && <div className="py-8 text-center border-t border-[#2A2B30]"><p className="text-xs text-gray-500">点击上方「AI 生成导言」或「AI 生成总结」来丰富专题概览</p></div>}
    </div>}

    {tab === 'paper' && <div className="space-y-6">
      {series.paper ? <div>
        <div className="series-context-heading flex items-center gap-2 mb-3">
          <span className="text-[11px] text-sky-400 font-medium">深度分析</span>
          <span className="text-[10px] text-gray-600">论文/讲稿式</span>
          {embedded && <button className="series-context-action series-paper-action" onClick={handleGeneratePaper} disabled={anyGenerating || memberCount < 2}>
            {paperGenerating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}重新生成
          </button>}
        </div>
        <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-line ref-container" onClick={(event) => {
          const element = (event.target as HTMLElement).closest('.ref-link') as HTMLElement | null;
          const reference = parseInt(element?.dataset.ref || '0');
          if (reference > 0) handleRefClick(reference);
        }} dangerouslySetInnerHTML={{ __html: paperHtml }} />
      </div> : <div className="series-context-empty-state py-12 text-center">
        <p className="text-xs text-gray-500">尚未生成深度分析</p>
        {embedded && <button className="series-context-action series-paper-action" onClick={handleGeneratePaper} disabled={anyGenerating || memberCount < 2}><Sparkles size={12} />生成深度分析</button>}
      </div>}
    </div>}
  </>;
}
