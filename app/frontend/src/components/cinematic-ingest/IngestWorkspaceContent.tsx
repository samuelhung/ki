import { useMemo } from 'react';
import type { ChangeEvent, MouseEvent } from 'react';
import { createPortal } from 'react-dom';
import { FileText, Link2, Radio, Search, Sparkles } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { EmbeddedIngestList } from '../ingest/EmbeddedIngestList';
import { EmbeddedIngestWorkspace } from '../ingest/EmbeddedIngestWorkspace';
import { ContentDetailPanel } from './ContentDetailPanel';
import type { useIngestDetailActions } from './useIngestDetailActions';
import type { DetailTab, EventItem, TopicKey } from './ingestTypes';

const DETAIL_TABS: Array<{ key: DetailTab; label: string; meta: string; icon: LucideIcon }> = [
  { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: FileText },
  { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: Sparkles },
  { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: Link2 },
  { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: Radio },
];

type DetailActions = ReturnType<typeof useIngestDetailActions>;

interface IngestWorkspaceContentProps {
  events: EventItem[];
  activeEventId: string | null;
  activeTopic: TopicKey;
  loading: boolean;
  loadingMore: boolean;
  total: number;
  hasMore: boolean;
  error: string;
  search: string;
  searchPortalTarget: HTMLElement | null;
  selectedEvent: EventItem | null;
  details: DetailActions;
  titleActions: React.ReactNode;
  transcriptStatus: React.ReactNode;
  transcriptContent?: string;
  summaryStale: boolean;
  onRetry: () => void;
  onLoadMore: () => void;
  onSelect: (eventId: string) => void;
  onDelete: (eventId: string, event: MouseEvent) => void;
  onTopicChange: (topic: TopicKey) => void;
  onSearchChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSummarize: () => void;
  onContemplate: () => void;
  onToggleQuestion: (questionId: string) => void;
  onLinkQuestions: () => void;
  onChainAnalyze: () => void;
  onSyncHints: () => void;
}

export function IngestWorkspaceContent({
  events,
  activeEventId,
  activeTopic,
  loading,
  loadingMore,
  total,
  hasMore,
  error,
  search,
  searchPortalTarget,
  selectedEvent,
  details,
  titleActions,
  transcriptStatus,
  transcriptContent,
  summaryStale,
  onRetry,
  onLoadMore,
  onSelect,
  onDelete,
  onTopicChange,
  onSearchChange,
  onSummarize,
  onContemplate,
  onToggleQuestion,
  onLinkQuestions,
  onChainAnalyze,
  onSyncHints,
}: IngestWorkspaceContentProps) {
  const detailTabs = useMemo(() => (
    <nav className="ingest-detail-tabs" aria-label="内容详情维度">
      {DETAIL_TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.key}
            type="button"
            className={`ingest-tab-trigger launcher-action pixel-command is-${tab.key}${details.detailTab === tab.key ? ' is-active' : ''}`}
            onClick={() => {
              details.setDetailTab(tab.key);
              if (tab.key === 'summary' && details.detail && !details.detail.ai_summary && details.summarizingId !== details.detail.id) {
                details.handleSummarize(details.detail.id);
              }
              if (tab.key === 'chain' && details.detail && !details.chainAnalysis && !details.chainLoading) {
                details.handleChainAnalyze();
              }
            }}
          >
            <Icon size={15} />
            <b>{tab.label}</b>
            <span>{tab.meta}</span>
          </button>
        );
      })}
    </nav>
  ), [
    details.chainAnalysis,
    details.chainLoading,
    details.detail,
    details.detailTab,
    details.handleChainAnalyze,
    details.handleSummarize,
    details.setDetailTab,
    details.summarizingId,
  ]);

  const list = useMemo(() => (
    <EmbeddedIngestList
      events={events}
      activeEventId={activeEventId}
      activeTopic={activeTopic}
      loading={loading}
      loadingMore={loadingMore}
      total={total}
      hasMore={hasMore}
      error={error}
      onRetry={onRetry}
      onLoadMore={onLoadMore}
      onSelect={onSelect}
      onDelete={onDelete}
    />
  ), [activeEventId, activeTopic, error, events, hasMore, loading, loadingMore, onDelete, onLoadMore, onRetry, onSelect, total]);

  const searchAccessory = useMemo(() => (
    <label className="ki-ingest-list-search">
      <Search size={14} />
      <input value={search} onChange={onSearchChange} placeholder="搜索内容标题" />
    </label>
  ), [onSearchChange, search]);

  const detail = useMemo(() => (
    <ContentDetailPanel
      detail={details.detail}
      fallback={selectedEvent}
      loading={details.detailLoading}
      error={details.detailError}
      tab={details.detailTab}
      detailTabs={detailTabs}
      titleActions={titleActions}
      transcriptStatus={transcriptStatus}
      transcriptContent={transcriptContent}
      summaryStale={summaryStale}
      summarizing={Boolean(details.detail && details.summarizingId === details.detail.id)}
      contemplating={details.contemplating}
      contemplateError={details.contemplateError}
      contemplateResults={details.contemplateResults}
      contemplateSelected={details.contemplateSelected}
      contemplateLinking={details.contemplateLinking}
      linkedQuestions={details.linkedQuestions}
      linkedQuestionsLoading={details.linkedQuestionsLoading}
      chainAnalysis={details.chainAnalysis}
      chainLoading={details.chainLoading}
      chainError={details.chainError}
      chainHints={details.chainHints}
      syncingHints={details.syncingHints}
      syncResult={details.syncResult}
      onSummarize={onSummarize}
      onContemplate={onContemplate}
      onToggleQuestion={onToggleQuestion}
      onLinkQuestions={onLinkQuestions}
      onChainAnalyze={onChainAnalyze}
      onSyncHints={onSyncHints}
    />
  ), [detailTabs, details, onChainAnalyze, onContemplate, onLinkQuestions, onSummarize, onSyncHints, onToggleQuestion, selectedEvent, summaryStale, titleActions, transcriptContent, transcriptStatus]);

  return (
    <EmbeddedIngestWorkspace
      activeTopic={activeTopic}
      onTopicChange={onTopicChange}
      list={list}
      detail={detail}
      accessory={searchPortalTarget ? createPortal(searchAccessory, searchPortalTarget) : null}
    />
  );
}
