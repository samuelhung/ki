import { useCallback } from 'react';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { EventDetailBody } from '../components/cinematic-ingest/EventDetailBody';
import { EventDetailHeader } from '../components/cinematic-ingest/EventDetailHeader';
import { useEventDetail } from '../components/cinematic-ingest/useEventDetail';

export interface EventDetailData {
  id: string; source_id: string; title: string; title_cn?: string;
  url: string; topic: string; status: string; created_at: string;
  raw_summary?: string; ai_summary?: string; overview?: string; last_error?: string;
  summary_cn?: string; translation_status?: string;
  transcript_path?: string; summary_path?: string;
  video_path?: string; video_url?: string; audio_path?: string; document_path?: string;
  associated_questions?: any[];
}

export type TranscriptRevisionKind = 'original' | 'manual' | 'segmented' | 'restored';

export interface TranscriptRevisionMeta {
  id: string;
  kind: TranscriptRevisionKind;
  parent_revision_id?: string;
  source_revision_id?: string;
  created_at: string;
}

export interface TranscriptSnapshot {
  event_id: string;
  content: string;
  active_revision: TranscriptRevisionMeta;
  revisions: TranscriptRevisionMeta[];
  can_segment: boolean;
  summary_stale: boolean;
  artifact_synced: boolean;
}

export interface SegmentationTaskSnapshot {
  id: string;
  status: 'processing' | 'ready' | 'failed' | 'confirmed';
  base_revision_id: string;
  completed_chunks: number;
  total_chunks: number;
  preview?: string;
  error_code?: string;
}

export interface EventLinkedQuestion {
  id: any;
  question: any;
  topic?: any;
}

export interface EventContemplateSuggestion {
  question_id: any;
  question_text: any;
  link_status: any;
  relevance: any;
}

export interface EventChainHint {
  node_name: any;
  field: any;
  value: any;
}

export interface EventChainAnalyzeResponse {
  analysis?: any;
  extracted_hints?: any;
  error?: any;
}

interface EventDetailPageProps {
  embedded?: boolean;
  eventId?: string;
  onEventChange?: (event: EventDetailData | null) => void;
}

export default function EventDetailPage({ embedded = false, eventId, onEventChange }: EventDetailPageProps) {
  const { id: routeId } = useParams<{ id: string }>();
  const id = eventId || routeId;
  const navigate = useNavigate();
  const handleDetailChange = useCallback((event: EventDetailData) => {
    onEventChange?.(event);
  }, [onEventChange]);
  const {
    detail, loading, tab, setTab, mediaUrl, summarizingId, contemplating,
    contemplateError, contemplateResults, contemplateSelected, contemplateLinking,
    linkedQuestions, linkedQuestionsLoading, chainAnalysis, chainLoading, chainError,
    chainHints, syncingHints, syncResult, chainSuggestionsCount, handleSummarize,
    handleContemplate, handleContemplateLink, handleChainAnalyze, handleSyncHints,
    toggleQuestion,
  } = useEventDetail({ id, onDetailChange: handleDetailChange });

  if (loading) {
    return (
      <div className={`flex-1 flex items-center justify-center${embedded ? ' event-detail-embedded-state' : ' bg-[#0B0C10]'}`}>
        <Loader2 size={24} className="animate-spin text-gray-600" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className={`flex-1 text-white p-8${embedded ? ' event-detail-embedded-state' : ' bg-[#0B0C10]'}`}>
        <div className="max-w-[1080px] mx-auto py-16 text-center">
          <p className="text-sm text-red-400">内容不存在</p>
          <button onClick={() => navigate(-1)} className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">返回</button>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex-1 text-white overflow-y-auto custom-scrollbar ${embedded ? 'event-detail-embedded' : 'bg-[#0B0C10] p-4 md:p-8'}`}>
      <div className={embedded ? 'event-detail-embedded__inner' : 'max-w-[1080px] mx-auto'}>
        {!embedded && <div className="flex items-center mb-6">
          <button onClick={() => navigate('/ingest')} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors">
            <ArrowLeft size={14} /> 内容采集
          </button>
        </div>}
        <EventDetailHeader
          detail={detail}
          mediaUrl={mediaUrl}
          summarizingId={summarizingId}
          contemplating={contemplating}
          onSummarize={handleSummarize}
          onContemplate={handleContemplate}
          onAddTask={() => navigate(`/tasks?source=content&source_id=${id}&source_label=来自内容：${detail.title || ''}`)}
        />
        <EventDetailBody
          detail={detail}
          tab={tab}
          summarizingId={summarizingId}
          contemplating={contemplating}
          contemplateError={contemplateError}
          contemplateResults={contemplateResults}
          contemplateSelected={contemplateSelected}
          contemplateLinking={contemplateLinking}
          linkedQuestions={linkedQuestions}
          linkedQuestionsLoading={linkedQuestionsLoading}
          chainAnalysis={chainAnalysis}
          chainLoading={chainLoading}
          chainError={chainError}
          chainHints={chainHints}
          syncingHints={syncingHints}
          syncResult={syncResult}
          chainSuggestionsCount={chainSuggestionsCount}
          onTabChange={setTab}
          onSummarize={handleSummarize}
          onContemplate={handleContemplate}
          onLinkQuestions={handleContemplateLink}
          onChainAnalyze={handleChainAnalyze}
          onSyncHints={handleSyncHints}
          onToggleQuestion={toggleQuestion}
        />
      </div>
    </div>
  );
}
