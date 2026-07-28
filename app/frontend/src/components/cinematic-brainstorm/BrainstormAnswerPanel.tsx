import type React from 'react';
import { Loader2, Search } from 'lucide-react';

import type {
  BrainstormConcept,
  BrainstormDetailMode,
  BrainstormEventItem,
  BrainstormSuggestion,
} from './useBrainstormDetail';

export function sourceLabel(source_id: string): string {
  switch (source_id) {
    case 'douyin': return '抖音';
    case 'user-upload': return '上传';
    case 'user-concept': return '概念';
    default: return source_id;
  }
}

export function renderMarkdownWithRefs(content: string, lockedIds: string[],
  eventTitleMap: Map<string, string>,
  onReferenceClick: (eventId: string) => void,
  className: string = 'text-sm',
): React.ReactNode {
  if (!content) return <p className="text-gray-500 py-4 text-center">暂无内容</p>;

  let md = content.replace(/^好的，[^。\n]+。\n\n/, '');
  md = md.replace(/^根据(所选|您提供的)文章(内容)?[，,]\s*[^。\n]*[。，：:]\s*/s, '');
  const lines = md.split('\n');
  const nodes: React.ReactNode[] = [];
  let lineIndex = 0;
  let listItems: string[] = [];

  function renderInlineWithRefs(text: string): React.ReactNode {
    const parts = text.split(/(\*\*.+?\*\*|\[文档\d+\]|（证据：[^）]*）)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={index} className="font-semibold text-gray-200">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('（证据：')) return <span key={index} className="text-gray-500 italic">{part}</span>;
      const refMatch = part.match(/^\[文档(\d+)\]$/);
      if (!refMatch) return part;
      const eventId = lockedIds[parseInt(refMatch[1]) - 1];
      if (!eventId) return <span key={index}>{part}</span>;
      return (
        <span
          key={index}
          className="text-purple-400 bg-purple-500/10 px-1 rounded cursor-pointer hover:bg-purple-500/20 transition-colors"
          onClick={(event) => { event.stopPropagation(); onReferenceClick(eventId); }}
          title={eventTitleMap.get(eventId) || '点击查看文档详情'}
        >
          {part}
        </span>
      );
    });
  }

  function flushList() {
    if (listItems.length === 0) return;
    nodes.push(
      <ul key={`ul-${lineIndex}`} className="space-y-1 mt-1 mb-3">
        {listItems.map((item, index) => (
          <li key={index} className="flex gap-1.5">
            <span className="text-gray-500 shrink-0">•</span>
            <span className="text-gray-300">{renderInlineWithRefs(item)}</span>
          </li>
        ))}
      </ul>,
    );
    listItems = [];
  }

  for (lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const line = lines[lineIndex];
    if (line.startsWith('## ')) {
      flushList();
      nodes.push(<h3 key={lineIndex} className="text-sm font-semibold text-purple-400 mt-5 mb-2">{line.slice(3)}</h3>);
    } else if (line.startsWith('### ')) {
      flushList();
      nodes.push(<p key={lineIndex} className="mb-2 text-purple-400 leading-relaxed font-medium">{line.slice(4)}</p>);
    } else if (/^- /.test(line)) {
      listItems.push(line.replace(/^- /, ''));
    } else if (line.trim() === '' || /^[-*]{3,}$/.test(line.trim())) {
      flushList();
    } else {
      flushList();
      nodes.push(<p key={lineIndex} className="mb-2 text-gray-300 leading-relaxed">{renderInlineWithRefs(line)}</p>);
    }
  }
  flushList();
  return <div className={className}>{nodes}</div>;
}

interface BrainstormAnswerPanelProps {
  mode: Exclude<BrainstormDetailMode, 'chat'>;
  availableEvents: BrainstormEventItem[];
  filteredEvents: BrainstormEventItem[];
  selectedEventIds: Set<string>;
  lockedEventIds: Set<string>;
  judgedEvents: Map<string, string>;
  eventsLoading: boolean;
  eventSearch: string;
  contemplateError: string;
  contemplateResults: BrainstormSuggestion[];
  contemplateSelected: Set<string>;
  contemplateLinking: boolean;
  summary: string;
  summaryLoading: boolean;
  summaryUpdated: boolean;
  summaryCreatedAt: string;
  conversationLockedIds: string[];
  concepts: BrainstormConcept[];
  conceptsLoading: boolean;
  precipitatingName: string;
  onEventSearchChange: (value: string) => void;
  onToggleEvent: (eventId: string) => void;
  onToggleContemplateEvent: (eventId: string) => void;
  onSelectAllEvents: () => void;
  onDeselectAllEvents: () => void;
  onLinkContemplatedEvents: () => void;
  onGenerateSummary: () => void;
  onLoadConcepts: () => void;
  onPrecipitateConcept: (name: string, description: string) => void;
  onReferenceClick: (eventId: string) => void;
}

export default function BrainstormAnswerPanel(props: BrainstormAnswerPanelProps) {
  const eventTitleMap = new Map(props.availableEvents.map((event) => [event.id, event.title_cn || event.title]));

  if (props.mode === 'summary') {
    return (
      <div className="space-y-6">
        {props.summaryUpdated && (
          <div className="text-xs text-amber-400/80 bg-amber-500/5 border border-amber-500/15 rounded-lg px-3 py-2 flex items-center justify-between">
            <span>对话已更新，总结可能已过期</span>
            <button onClick={props.onGenerateSummary} disabled={props.summaryLoading}
              className="ml-2 px-2 py-1 text-[10px] rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-40 shrink-0">
              {props.summaryLoading ? '生成中...' : '生成总结'}
            </button>
          </div>
        )}
        {props.summary ? (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="w-1 h-3 rounded-full bg-amber-400" />
              <span className="text-xs text-amber-400 font-medium">📝 AI 深度总结</span>
              {props.summaryCreatedAt && <span className="text-[10px] text-gray-600 ml-auto">{props.summaryCreatedAt.slice(0, 16).replace('T', ' ')}</span>}
            </div>
            <div className="text-gray-300 leading-relaxed text-sm">
              {renderMarkdownWithRefs(props.summary, props.conversationLockedIds, eventTitleMap, props.onReferenceClick, '')}
            </div>
          </div>
        ) : (
          <div className="py-12 text-center"><p className="text-xs text-gray-500">在"参考文档"中勾选文档并发起问答后，可生成总结</p></div>
        )}
      </div>
    );
  }

  if (props.mode === 'concepts') {
    return (
      <div>
        {props.conceptsLoading ? (
          <div className="flex items-center justify-center py-12"><Loader2 size={20} className="animate-spin text-gray-600" /></div>
        ) : props.concepts.length === 0 ? (
          <div className="py-12 text-center"><p className="text-xs text-gray-500">{props.summary ? '总结中未找到相关概念' : '请先生成总结'}</p></div>
        ) : (
          <div className="space-y-3">
            {props.concepts.map((concept) => (
              <div key={concept.name} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-200 mb-1.5">{concept.name}</p>
                    <p className="text-xs text-gray-400 leading-relaxed">{concept.description}</p>
                  </div>
                  <div className="shrink-0">
                    {concept.precipitated ? (
                      <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20">已沉淀 ✓</span>
                    ) : (
                      <button onClick={() => props.onPrecipitateConcept(concept.name, concept.description)}
                        disabled={props.precipitatingName === concept.name}
                        className="text-[10px] font-medium text-purple-400 bg-purple-500/10 px-2 py-1 rounded border border-purple-500/20 hover:bg-purple-500/20 transition-colors disabled:opacity-50">
                        {props.precipitatingName === concept.name ? '沉淀中...' : '沉淀'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2A2B30]">
        <span className="text-xs text-gray-400 font-medium">{props.contemplateResults.length > 0 ? '凝神静思结果' : '全部可用文档'}</span>
        <div className="flex gap-2 items-center">
          {props.contemplateResults.length === 0 && <>
            <button onClick={props.onSelectAllEvents} className="text-[11px] text-gray-500 hover:text-gray-300">全选</button>
            <button onClick={props.onDeselectAllEvents} className="text-[11px] text-gray-500 hover:text-gray-300">清空</button>
          </>}
        </div>
      </div>
      {props.contemplateError && <div className="mx-4 mt-3 px-3 py-1.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{props.contemplateError}</div>}
      {props.contemplateResults.length > 0 ? (
        <div className="p-4">
          <div className="bg-[#0B0C10] rounded-lg p-3 border border-amber-500/10">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] text-amber-400 font-medium">找到 {props.contemplateResults.length} 条可能相关的文档</span>
              <button onClick={props.onLinkContemplatedEvents} disabled={props.contemplateLinking || props.contemplateSelected.size === 0}
                className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/20 transition-colors disabled:opacity-50">
                {props.contemplateLinking ? '关联中…' : `确认关联 (${props.contemplateSelected.size})`}
              </button>
            </div>
            <div className="space-y-0.5 max-h-64 overflow-y-auto custom-scrollbar">
              {props.contemplateResults.map((item) => {
                const isChecked = props.contemplateSelected.has(item.event_id);
                return (
                  <label key={item.event_id} className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-[#1A1B20] transition-colors text-[11px] ${isChecked ? 'bg-amber-500/10' : ''}`}>
                    <input type="checkbox" checked={isChecked} onChange={() => props.onToggleContemplateEvent(item.event_id)} className="w-3 h-3 rounded accent-amber-500 shrink-0" />
                    <span className="text-gray-300 truncate flex-1">{item.event_title}</span>
                    <span className={`text-[10px] font-medium px-1 py-0.5 rounded shrink-0 ${item.relevance === 'high' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'}`}>
                      {item.relevance === 'high' ? '高' : '中'}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      ) : <DocumentList {...props} />}
    </div>
  );
}

function DocumentList(props: BrainstormAnswerPanelProps) {
  return <>
    <div className="px-4 pt-3 pb-2">
      <div className="relative">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
        <input value={props.eventSearch} onChange={(event) => props.onEventSearchChange(event.target.value)} placeholder="搜索文档..."
          className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-xs text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50" />
      </div>
    </div>
    <div className="px-4 pb-3 space-y-0.5 max-h-80 overflow-y-auto custom-scrollbar">
      {props.eventsLoading ? (
        <div className="text-gray-500 text-xs py-4 text-center">加载中...</div>
      ) : props.filteredEvents.length === 0 ? (
        <div className="text-gray-500 text-xs py-4 text-center">无匹配文档</div>
      ) : props.filteredEvents.map((event) => {
        const selected = props.selectedEventIds.has(event.id);
        const locked = props.lockedEventIds.has(event.id);
        return (
          <label key={event.id} className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-[#1A1B20] transition-colors text-xs ${selected ? 'bg-purple-500/10' : ''} ${locked ? 'cursor-not-allowed opacity-80' : ''}`}>
            <input type="checkbox" checked={selected} disabled={locked} onChange={() => props.onToggleEvent(event.id)} className="w-3.5 h-3.5 rounded accent-purple-500 shrink-0" />
            <span className={`truncate flex-1 ${selected ? 'text-white' : 'text-gray-400'}`}>
              {locked && <span className="text-amber-500 mr-1" title="已回答过，锁定">🔒</span>}
              {event.content_type === 'concept' && <span className="text-emerald-400 mr-1" title="概念">📘</span>}
              {event.title_cn || event.title}
            </span>
            {props.judgedEvents.has(event.id) && (
              <span className={`text-[10px] font-medium px-1 py-0.5 rounded shrink-0 ${
                props.judgedEvents.get(event.id) === 'high' ? 'bg-emerald-500/15 text-emerald-400'
                  : props.judgedEvents.get(event.id) === 'medium' ? 'bg-amber-500/15 text-amber-400' : 'bg-gray-500/15 text-gray-400'
              }`}>
                {props.judgedEvents.get(event.id) === 'high' ? '高' : props.judgedEvents.get(event.id) === 'medium' ? '中' : '低'}
              </span>
            )}
            <span className="text-[10px] text-gray-600 shrink-0">{sourceLabel(event.source_id)}</span>
            {!!event.ai_summary && <span className="text-[10px] text-purple-500 shrink-0">AI</span>}
          </label>
        );
      })}
    </div>
  </>;
}
