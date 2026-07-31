import { Link2, Loader2, Sparkles } from 'lucide-react';
import { renderMarkdown } from '../MarkdownRenderer';
import type {
  EventChainHint, EventContemplateSuggestion, EventDetailData, EventLinkedQuestion,
} from '../../pages/EventDetailPage';
import type { EventDetailTab } from './useEventDetail';

interface EventDetailBodyProps {
  detail: EventDetailData;
  tab: EventDetailTab;
  summarizingId: string | null;
  contemplating: boolean;
  contemplateError: string;
  contemplateResults: EventContemplateSuggestion[];
  contemplateSelected: Set<string>;
  contemplateLinking: boolean;
  linkedQuestions: EventLinkedQuestion[];
  linkedQuestionsLoading: boolean;
  chainAnalysis: string;
  chainLoading: boolean;
  chainError: string;
  chainHints: EventChainHint[];
  syncingHints: boolean;
  syncResult: string;
  chainSuggestionsCount: number;
  transcriptContent?: string;
  summaryStale: boolean;
  onTabChange: (tab: EventDetailTab) => void;
  onSummarize: (eventId: string) => void;
  onContemplate: () => void;
  onLinkQuestions: () => void;
  onChainAnalyze: () => void;
  onSyncHints: () => void;
  onToggleQuestion: (questionId: string) => void;
}

export function EventDetailBody(props: EventDetailBodyProps) {
  const { detail, tab, summarizingId, chainAnalysis, chainLoading, chainSuggestionsCount } = props;
  const supportedSource = ['douyin', 'user-upload', 'user-concept'].includes(detail.source_id);
  return <>
    {supportedSource && <div className="flex items-center justify-between mb-6 border-b border-[#2A2B30]">
      <div className="flex gap-4">
        {detail.source_id !== 'user-concept' && <button onClick={() => props.onTabChange('body')}
          className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'body' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
          转写原文
        </button>}
        <button onClick={() => { props.onTabChange('summary'); if (!detail.ai_summary && summarizingId !== detail.id) props.onSummarize(detail.id); }}
          className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'summary' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
          {summarizingId === detail.id ? '生成中…' : detail.source_id === 'user-concept' ? '概念详解' : 'AI 总结'}
        </button>
        <button onClick={() => props.onTabChange('questions')}
          className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'questions' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
          关联问题
        </button>
        <button onClick={() => { props.onTabChange('chain'); if (!chainAnalysis && !chainLoading) props.onChainAnalyze(); }}
          className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'chain' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
          {chainLoading ? '分析中…' : <>产业分析{chainSuggestionsCount > 0 && <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 text-[10px]">{chainSuggestionsCount}</span>}</>}
        </button>
      </div>
    </div>}
    <div className="min-h-[30vh]">
      {supportedSource ? <>
        {tab === 'body' && <EventBody detail={detail} transcriptContent={props.transcriptContent} />}
        {tab === 'summary' && <EventSummary {...props} />}
        {tab === 'questions' && <EventQuestions {...props} />}
        {tab === 'chain' && <EventChain {...props} />}
      </> : <>
        <EventBody detail={detail} />
        <EventQuestions {...props} />
      </>}
      {detail.last_error && <div className="mt-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">⚠️ {detail.last_error}</div>}
    </div>
  </>;
}

function EventBody({ detail, transcriptContent }: { detail: EventDetailData; transcriptContent?: string }) {
  const bodyText = transcriptContent ?? detail.raw_summary;
  return <div className="text-sm leading-relaxed text-gray-300 space-y-2">
    {bodyText ? <div className="whitespace-pre-wrap">{bodyText}</div> : <p className="text-gray-500 py-12 text-center">暂无转写内容</p>}
  </div>;
}

function EventSummary(props: EventDetailBodyProps) {
  const { detail, summarizingId } = props;
  const hasOverview = !!detail.overview;
  if (summarizingId === detail.id && !detail.ai_summary) {
    return <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-purple-400" /></div>;
  }
  return <div className="space-y-6 text-sm">
    {props.summaryStale && <div className="summary-stale-notice">
      <div><Sparkles size={15} /><span>原文已更新，可重新生成 AI 总结</span></div>
      <button type="button" onClick={() => props.onSummarize(detail.id)} disabled={summarizingId === detail.id}>
        {summarizingId === detail.id ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
        {summarizingId === detail.id ? '正在重新生成' : '重新生成 AI 总结'}
      </button>
    </div>}
    {hasOverview && <div>
      <div className="flex items-center gap-2 mb-3"><span className="w-1 h-4 rounded-full bg-purple-400" /><span className="text-xs text-purple-400 font-medium">内容概述</span></div>
      <div className="text-gray-300 leading-relaxed whitespace-pre-wrap text-sm">{detail.overview}</div>
    </div>}
    {detail.ai_summary ? <div className={hasOverview ? 'pt-6 border-t border-[#2A2B30]' : ''}>
      {hasOverview && <div className="flex items-center gap-2 mb-3"><span className="w-1 h-4 rounded-full bg-amber-400" /><span className="text-xs text-amber-400 font-medium">AI 深度总结</span></div>}
      {renderMarkdown(detail.ai_summary)}
    </div> : <div className={hasOverview ? 'pt-6 border-t border-[#2A2B30]' : ''}>
      <div className="text-center py-10">
        <p className="text-gray-500 mb-4">{hasOverview ? '概述已生成，可补充完整 AI 总结' : '该内容尚未生成 AI 总结'}</p>
        <button onClick={() => props.onSummarize(detail.id)} className="px-5 py-2.5 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">生成 AI 总结</button>
      </div>
    </div>}
  </div>;
}

function EventQuestions(props: EventDetailBodyProps) {
  const unlinkedResults = props.contemplateResults.filter((suggestion) => suggestion.link_status !== 'linked');
  return <div>
    {props.linkedQuestions.length > 0 && <div className="mb-4">
      <span className="text-xs text-purple-400 font-medium">已关联问题 · {props.linkedQuestions.length} 条</span>
      <div className="mt-2 space-y-1.5">{props.linkedQuestions.map((question) => <div key={question.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-500/10 border border-purple-500/15">
        <span className="text-purple-400 text-xs shrink-0">🔗</span><span className="text-gray-300 truncate flex-1 text-sm">{question.question}</span>
        {question.topic && <span className="text-xs text-gray-500 bg-[#141518] px-2 py-1 rounded shrink-0">{question.topic}</span>}
      </div>)}</div>
    </div>}
    {props.linkedQuestionsLoading && <div className="flex items-center gap-2 text-gray-500 py-2 mb-2"><Loader2 size={12} className="animate-spin" /><span className="text-xs">加载已关联问题…</span></div>}
    {props.contemplateError && <div className="mb-3 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{props.contemplateError}</div>}
    {props.contemplating && props.contemplateResults.length === 0 && <div className="flex items-center gap-2 text-gray-500 py-3"><Loader2 size={14} className="animate-spin" /><span className="text-sm">匹配关联问题中…</span></div>}
    <div className="flex items-center justify-between mb-3">
      <span className="text-xs text-gray-400 font-medium">{unlinkedResults.length > 0 ? <>推荐关联 · {unlinkedResults.length} 条</> : '推荐关联'}</span>
      <div className="flex items-center gap-2">
        {unlinkedResults.length > 0 && <button onClick={props.onLinkQuestions} disabled={props.contemplateLinking || props.contemplateSelected.size === 0}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/20 transition-colors disabled:opacity-50">
          {props.contemplateLinking ? '关联中…' : `确认关联 (${props.contemplateSelected.size})`}
        </button>}
        <button onClick={props.onContemplate} disabled={props.contemplating}
          className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-50">
          <Sparkles size={12} />{props.contemplating ? '思考中…' : '凝神静思'}
        </button>
      </div>
    </div>
    {unlinkedResults.length > 0 ? <div className="space-y-1.5">{unlinkedResults.map((item) => {
      const isChecked = props.contemplateSelected.has(item.question_id);
      const relevanceLabel = item.relevance === 'high' ? '高' : item.relevance === 'medium' ? '中' : '低';
      const relevanceClass = item.relevance === 'high' ? 'bg-emerald-500/15 text-emerald-400' : item.relevance === 'medium' ? 'bg-amber-500/15 text-amber-400' : 'bg-gray-500/15 text-gray-400';
      return <div key={item.question_id} className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer hover:bg-[#1A1B20] transition-colors ${isChecked ? 'bg-purple-500/10 border border-purple-500/20' : ''}`} onClick={() => props.onToggleQuestion(item.question_id)}>
        <input type="checkbox" checked={isChecked} readOnly className="w-4 h-4 rounded accent-purple-500 shrink-0 pointer-events-none" />
        <span className="text-gray-300 truncate flex-1 text-sm">{item.question_text}</span><span className={`text-xs font-medium px-2 py-0.5 rounded shrink-0 ${relevanceClass}`}>{relevanceLabel}</span>
      </div>;
    })}</div> : !props.contemplating && !props.contemplateError && <div className="text-center py-4"><p className="text-gray-500 text-xs">暂无推荐关联</p></div>}
  </div>;
}

function EventChain(props: EventDetailBodyProps) {
  if (props.chainLoading) return <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-purple-400" /></div>;
  if (props.chainError) return <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{props.chainError}</div>;
  if (!props.chainAnalysis) return <div className="text-center py-10">
    <p className="text-gray-500 mb-4 text-sm">基于知识库分析事件对各产业链的影响</p>
    <button onClick={props.onChainAnalyze} className="px-5 py-2.5 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">开始分析</button>
  </div>;
  return <div className="text-sm leading-relaxed text-gray-300 space-y-3">
    {renderMarkdown(props.chainAnalysis)}
    {props.chainHints.length > 0 && <div className="mt-4 bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-xs font-medium text-emerald-400"><Link2 size={14} />从分析中提取到 {props.chainHints.length} 个数据点</div>
        <button onClick={props.onSyncHints} disabled={props.syncingHints} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/20 disabled:opacity-50 transition-colors">{props.syncingHints ? '同步中…' : '同步到产业链'}</button>
      </div>
      <div className="space-y-1.5">{props.chainHints.slice(0, 5).map((hint, index) => <div key={index} className="flex items-center gap-2 text-[11px] bg-[#0B0C10] rounded-lg px-3 py-2">
        <span className="text-emerald-400 font-medium">{hint.node_name}</span><span className="text-gray-600">·</span><span className="text-gray-400">{hint.field}</span><span className="text-gray-600">→</span><span className="text-emerald-300">{hint.value}</span>
      </div>)}{props.chainHints.length > 5 && <div className="text-[10px] text-gray-600 pl-2">…及其他 {props.chainHints.length - 5} 条</div>}</div>
    </div>}
    {props.syncResult && <div className="px-4 py-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">{props.syncResult}</div>}
  </div>;
}
