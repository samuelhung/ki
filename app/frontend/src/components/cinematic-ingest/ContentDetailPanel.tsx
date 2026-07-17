import React, { memo } from 'react';
import { Link2, Loader2 } from 'lucide-react';
import { renderMarkdown } from '../MarkdownRenderer';
import { formatTimeBeijing, sourceLabel, statusLabel } from '../../utils';
import type { ChainHint, ContemplateSuggestion, DetailTab, EventItem, LinkedQuestion } from './ingestTypes';
import { ingestCopy } from './ingestCopy';

function ContentDetailPanelComponent({
  detail,
  fallback,
  loading,
  error,
  tab,
  detailTabs,
  summarizing,
  contemplating,
  contemplateError,
  contemplateResults,
  contemplateSelected,
  contemplateLinking,
  linkedQuestions,
  linkedQuestionsLoading,
  chainAnalysis,
  chainLoading,
  chainError,
  chainHints,
  syncingHints,
  syncResult,
  onSummarize,
  onContemplate,
  onToggleQuestion,
  onLinkQuestions,
  onChainAnalyze,
  onSyncHints,
}: {
  detail: EventItem | null;
  fallback: EventItem | null;
  loading: boolean;
  error: string;
  tab: DetailTab;
  detailTabs: React.ReactNode;
  summarizing: boolean;
  contemplating: boolean;
  contemplateError: string;
  contemplateResults: ContemplateSuggestion[];
  contemplateSelected: Set<string>;
  contemplateLinking: boolean;
  linkedQuestions: LinkedQuestion[];
  linkedQuestionsLoading: boolean;
  chainAnalysis: string;
  chainLoading: boolean;
  chainError: string;
  chainHints: ChainHint[];
  syncingHints: boolean;
  syncResult: string;
  onSummarize: () => void;
  onContemplate: () => void;
  onToggleQuestion: (questionId: string) => void;
  onLinkQuestions: () => void;
  onChainAnalyze: () => void;
  onSyncHints: () => void;
}) {
  const item = detail || fallback;

  function renderBody() {
    const bodyText = detail?.summary_cn || detail?.raw_summary;
    return bodyText ? (
      <div className="detail-markdown whitespace-pre-wrap">{bodyText}</div>
    ) : (
      <div className="detail-empty">{ingestCopy.detail.bodyEmpty}</div>
    );
  }

  function renderSummary() {
    if (summarizing) return <div className="detail-loading"><Loader2 size={20} className="animate-spin" /> {ingestCopy.detail.summaryLoading}</div>;
    const hasOverview = Boolean(detail?.overview);
    const hasAiSummary = Boolean(detail?.ai_summary);
    if (!hasOverview && !hasAiSummary) {
      return (
        <div className="detail-empty">
          <span>{ingestCopy.detail.summaryEmpty}</span>
          {detail && <button onClick={onSummarize}>{ingestCopy.detail.summaryAction}</button>}
        </div>
      );
    }
    return (
      <div className="detail-summary">
        {detail?.overview && (
          <section>
            <h3>内容概述</h3>
            <div className="detail-markdown whitespace-pre-wrap">{detail.overview}</div>
          </section>
        )}
        {detail?.ai_summary && (
          <section>
            <h3>AI 深度总结</h3>
            <div className="detail-markdown">{renderMarkdown(detail.ai_summary)}</div>
          </section>
        )}
      </div>
    );
  }

  function renderQuestions() {
    const unlinkedResults = contemplateResults.filter((item) => item.link_status !== 'linked');
    return (
      <div className="detail-questions">
        <div className="detail-action-row">
          <span>推荐关联</span>
          <div>
            {unlinkedResults.length > 0 && (
              <button onClick={onLinkQuestions} disabled={contemplateLinking || contemplateSelected.size === 0}>
                {contemplateLinking ? '关联中' : `确认关联 ${contemplateSelected.size}`}
              </button>
            )}
            <button onClick={onContemplate} disabled={!detail || contemplating}>
              {contemplating ? '思考中' : '凝神静思'}
            </button>
          </div>
        </div>
        {contemplateError && <div className="detail-error">{contemplateError}</div>}
        {linkedQuestionsLoading && <div className="detail-loading"><Loader2 size={16} className="animate-spin" /> {ingestCopy.detail.questionsLoading}</div>}
        {linkedQuestions.length > 0 && (
          <section>
            <h3>已关联问题 · {linkedQuestions.length} 条</h3>
            {linkedQuestions.map((question) => (
              <div key={question.id} className="question-row">
                <span>{question.question}</span>
                {question.topic && <em>{question.topic}</em>}
              </div>
            ))}
          </section>
        )}
        {unlinkedResults.length > 0 ? (
          <section>
            <h3>推荐关联 · {unlinkedResults.length} 条</h3>
            {unlinkedResults.map((question) => (
              <button
                key={question.question_id}
                className={`question-row is-clickable${contemplateSelected.has(question.question_id) ? ' is-selected' : ''}`}
                onClick={() => onToggleQuestion(question.question_id)}
              >
                <span>{question.question_text}</span>
                <em>{question.relevance === 'high' ? '高' : question.relevance === 'medium' ? '中' : '低'}</em>
              </button>
            ))}
          </section>
        ) : (
          !contemplating && <div className="detail-empty">{ingestCopy.detail.questionsEmpty}</div>
        )}
      </div>
    );
  }

  function renderChain() {
    if (chainLoading) return <div className="detail-loading"><Loader2 size={20} className="animate-spin" /> {ingestCopy.detail.chainLoading}</div>;
    if (chainError) return <div className="detail-error">{chainError}</div>;
    if (!chainAnalysis) {
      return (
        <div className="detail-empty">
          <span>{ingestCopy.detail.chainEmpty}</span>
          {detail && <button onClick={onChainAnalyze}>{ingestCopy.detail.chainAction}</button>}
        </div>
      );
    }
    return (
      <div className="detail-summary">
        <div className="detail-markdown">{renderMarkdown(chainAnalysis)}</div>
        {chainHints.length > 0 && (
          <section className="chain-hints">
            <div className="detail-action-row">
              <span><Link2 size={14} /> 提取到 {chainHints.length} 个数据点</span>
              <button onClick={onSyncHints} disabled={syncingHints}>{syncingHints ? '同步中' : '同步到产业链'}</button>
            </div>
            {chainHints.slice(0, 5).map((hint, index) => (
              <div key={`${hint.node_name}-${hint.field}-${index}`} className="hint-row">
                <b>{hint.node_name}</b>
                <span>{hint.field}</span>
                <em>{hint.value}</em>
              </div>
            ))}
          </section>
        )}
        {syncResult && <div className="detail-success">{syncResult}</div>}
      </div>
    );
  }

  let content: React.ReactNode;
  if (loading) content = <div className="detail-loading"><Loader2 size={20} className="animate-spin" /> {ingestCopy.detail.loading}</div>;
  else if (error) content = <div className="detail-error">{error}</div>;
  else if (!item) content = <div className="detail-empty">{ingestCopy.detail.empty}</div>;
  else if (!detail) content = <div className="detail-empty">{ingestCopy.detail.preparing}</div>;
  else if (tab === 'body') content = renderBody();
  else if (tab === 'summary') content = renderSummary();
  else if (tab === 'questions') content = renderQuestions();
  else content = renderChain();

  return (
    <section className="ingest-detail-reader" aria-label="内容详情">
      <header>
        <span>{item ? `${sourceLabel(item.source_id)} · ${statusLabel(item.status)}` : 'CONTENT DETAIL'}</span>
        <h2>{item?.title_cn || item?.title || ingestCopy.detail.titleFallback}</h2>
        {item && <small>{formatTimeBeijing(item.created_at)} · {item.topic || 'uncategorized'}</small>}
      </header>
      {detailTabs}
      <div className="detail-scroll-shell">
        <div className="detail-scroll">
          {content}
          {detail?.last_error && <div className="detail-error">{detail.last_error}</div>}
        </div>
      </div>
    </section>
  );
}

export const ContentDetailPanel = memo(ContentDetailPanelComponent);
