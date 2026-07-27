import React, { useCallback, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Lightbulb, Loader2, MessageSquare, Plus, Sparkles } from 'lucide-react';

import BrainstormAnswerPanel from '../components/cinematic-brainstorm/BrainstormAnswerPanel';
import BrainstormConversationPanel from '../components/cinematic-brainstorm/BrainstormConversationPanel';
import {
  useBrainstormDetail,
  type BrainstormDetailMode,
  type BrainstormQuestion,
} from '../components/cinematic-brainstorm/useBrainstormDetail';
import { formatTimeBeijing } from '../utils';

export type { BrainstormQuestion } from '../components/cinematic-brainstorm/useBrainstormDetail';

interface BrainstormDetailPageProps {
  embedded?: boolean;
  questionId?: string;
  onQuestionChange?: (question: BrainstormQuestion) => void;
  embeddedActions?: React.ReactNode;
}

export default function BrainstormDetailPage({
  embedded = false,
  questionId,
  onQuestionChange,
  embeddedActions,
}: BrainstormDetailPageProps) {
  const { id: routeId } = useParams<{ id: string }>();
  const id = questionId || routeId;
  const navigate = useNavigate();
  const [conceptTab, setConceptTab] = useState<BrainstormDetailMode>('docs');
  const handleQuestionLoaded = useCallback((question: BrainstormQuestion) => {
    onQuestionChange?.(question);
  }, [onQuestionChange]);
  const handleModeChange = useCallback((mode: BrainstormDetailMode) => setConceptTab(mode), []);
  const detail = useBrainstormDetail({
    questionId: id,
    selectedMode: conceptTab,
    onQuestionLoaded: handleQuestionLoaded,
    onModeChange: handleModeChange,
  });
  const {
    handleContemplate,
    handleContemplateLink,
    loadConcepts,
    generateSummary,
    precipitateConcept,
    sendFollowUp,
    startConversation,
    toggleContemplateEvent,
    toggleEvent,
  } = detail;

  function handleReferenceClick(eventId: string) {
    navigate(`/events/${eventId}`);
  }

  if (detail.loading) {
    return (
      <div className={`${embedded ? 'brainstorm-detail-embedded is-loading' : 'flex-1 bg-[#0B0C10]'} flex items-center justify-center`}>
        <Loader2 size={24} className="animate-spin text-gray-600" />
      </div>
    );
  }

  if (detail.notFound || !detail.question) {
    return (
      <div className={`${embedded ? 'brainstorm-detail-embedded is-error' : 'flex-1 bg-[#0B0C10] text-white p-8'}`}>
        <div className="max-w-[1080px] mx-auto py-16 text-center">
          <p className="text-sm text-red-400">问题不存在</p>
          <button onClick={() => navigate(-1)} className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">返回</button>
        </div>
      </div>
    );
  }

  const { question } = detail;
  const hasConversation = detail.conversationMessages.length > 0;
  const contentClassName = 'min-h-[30vh]';

  return (
    <div className={`${embedded ? 'brainstorm-detail-embedded is-ready' : 'flex-1 bg-[#0B0C10] text-white p-4 md:p-8 overflow-y-auto custom-scrollbar'}`}>
      <div className="max-w-[1080px] mx-auto">
        <div className={`flex items-center mb-6${embedded ? ' brainstorm-detail-back' : ''}`}>
          <button onClick={() => navigate('/brainstorm')} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors">
            <ArrowLeft size={14} /> 头脑风暴
          </button>
        </div>

        <div className="mb-6">
          <div className="brainstorm-detail-header flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb size={24} className="text-purple-400 shrink-0" />
                <h1 className="text-lg sm:text-xl font-bold leading-relaxed">{question.question}</h1>
              </div>
              {question.topic && <p className="text-sm text-gray-400">{question.topic}</p>}
              <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-600 flex-wrap">
                <span>{detail.lockedEventIds.size} 条文档</span>
                <span>创建于 {formatTimeBeijing(question.created_at)}</span>
                {question.updated_at && <span>更新于 {formatTimeBeijing(question.updated_at)}</span>}
              </div>
            </div>
            <div className="brainstorm-detail-actions flex items-center gap-1.5 sm:gap-2 shrink-0 flex-wrap">
              {embeddedActions}
              <button onClick={startConversation} disabled={detail.conversationLoading || detail.selectedEventIds.size === 0}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {detail.conversationLoading ? <Loader2 size={14} className="animate-spin" /> : <MessageSquare size={14} />}
                <span className="hidden sm:inline">发起问答</span>
              </button>
              <button onClick={handleContemplate} disabled={detail.contemplating}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {detail.contemplating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">凝神静思</span>
              </button>
              <button
                onClick={() => navigate(`/tasks?source=brainstorm&source_id=${id}&source_label=来自脑暴：${question?.title || ''}`)}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors flex items-center gap-1.5"
              >
                <Plus size={14} />
                <span className="hidden sm:inline">添加待办</span>
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between mb-6 border-b border-[#2A2B30]">
          <div className="flex gap-4">
            <button onClick={() => setConceptTab('chat')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'chat' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              💬 对话
              {hasConversation && <span className="ml-1 text-[10px] text-gray-600">({detail.conversationMessages.length})</span>}
            </button>
            <button onClick={() => setConceptTab('summary')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'summary' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              📝 总结
              {detail.summaryUpdated && <span className="ml-1.5 w-1.5 h-1.5 bg-amber-500 rounded-full inline-block" title="对话已更新" />}
            </button>
            <button onClick={() => { setConceptTab('concepts'); loadConcepts(); }}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'concepts' ? 'text-emerald-400 border-emerald-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              🧠 概念沉淀
            </button>
            <button onClick={() => setConceptTab('docs')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'docs' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              📄 参考文档
              <span className="ml-1 text-[10px] text-gray-600">({detail.selectedEventIds.size}/{detail.availableEvents.length})</span>
            </button>
          </div>
        </div>

        {conceptTab === 'chat' ? (
            <BrainstormConversationPanel
              contentClassName={contentClassName}
              messages={detail.conversationMessages}
              lockedEventIds={detail.conversationLockedIds}
              availableEvents={detail.availableEvents}
              followUpText={detail.followUpText}
              sendingFollowUp={detail.sendingFollowUp}
              error={detail.contemplateError}
              followUpInputRef={detail.followUpInputRef}
              onFollowUpTextChange={detail.setFollowUpText}
              onStartConversation={startConversation}
              onSendFollowUp={sendFollowUp}
              onReferenceClick={handleReferenceClick}
            />
          ) : (
          <div className={contentClassName}>
            <BrainstormAnswerPanel
              mode={conceptTab}
              availableEvents={detail.availableEvents}
              filteredEvents={detail.filteredEvents}
              selectedEventIds={detail.selectedEventIds}
              lockedEventIds={detail.lockedEventIds}
              judgedEvents={detail.judgedEvents}
              eventsLoading={detail.eventsLoading}
              eventSearch={detail.eventSearch}
              contemplateError={detail.contemplateError}
              contemplateResults={detail.contemplateResults}
              contemplateSelected={detail.contemplateSelected}
              contemplateLinking={detail.contemplateLinking}
              summary={detail.summary}
              summaryLoading={detail.summaryLoading}
              summaryUpdated={detail.summaryUpdated}
              summaryCreatedAt={detail.summaryCreatedAt}
              conversationLockedIds={detail.conversationLockedIds}
              concepts={detail.summaryConcepts}
              conceptsLoading={detail.conceptsLoading}
              precipitatingName={detail.precipitatingName}
              onEventSearchChange={detail.setEventSearch}
              onToggleEvent={toggleEvent}
              onToggleContemplateEvent={toggleContemplateEvent}
              onSelectAllEvents={detail.selectAllEvents}
              onDeselectAllEvents={detail.deselectAllEvents}
              onLinkContemplatedEvents={handleContemplateLink}
              onGenerateSummary={generateSummary}
              onLoadConcepts={loadConcepts}
              onPrecipitateConcept={precipitateConcept}
              onReferenceClick={handleReferenceClick}
            />
          </div>
          )}

        {conceptTab === 'summary' && (
          <div className="mt-4 pt-4 border-t border-[#2A2B30]">
            <button onClick={generateSummary} disabled={detail.summaryLoading}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              {detail.summaryLoading ? '生成中...' : (detail.summary ? '重新生成总结' : '生成总结')}
            </button>
          </div>
        )}
        {conceptTab === 'docs' && hasConversation && (
          <div className="mt-4 pt-4 border-t border-[#2A2B30]">
            <button onClick={() => setConceptTab('chat')}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">
              返回对话
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
