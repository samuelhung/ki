import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Clock3, ExternalLink, FileText, Loader2, Sparkles, Zap } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api';
import { fetchBriefingDetail, fetchBriefingHistory, generateQuickBriefing } from '../components/cinematic-briefings/briefingRequests.mjs';
import { briefingMetrics, resolveBriefingLoadSelection } from '../components/cinematic-briefings/briefingWorkspace.mjs';
import { RequestLifecycle } from '../components/ingest/requestLifecycle';
import SpotlightListRow from '../components/react-bits/SpotlightListRow';
import { formatTimeBeijing } from '../utils';
import KiNavigationShell from './KiNavigationShell';
import '../components/cinematic-ingest/cinematic-ingest.css';
import './CinematicBriefings.css';

type BriefingListItem = {
  id: string;
  type: 'quick' | 'daily';
  events_used: number;
  topic_count: number;
  created_at: string;
};

type BriefingEvent = {
  event_id: string;
  title_cn?: string;
  highlight?: string;
  source_name?: string;
  created_at?: string;
};

type BriefingTopic = {
  topic: string;
  topic_label?: string;
  summary?: string;
  events: BriefingEvent[];
};

type BriefingDetail = {
  id: string;
  type: 'quick' | 'daily';
  events_used: number;
  created_at: string;
  topics: BriefingTopic[];
};

function typeLabel(type: BriefingListItem['type']) {
  return type === 'daily' ? '深度日报' : '即时快报';
}

export default function CinematicBriefings() {
  const navigate = useNavigate();
  const [items, setItems] = useState<BriefingListItem[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<BriefingDetail | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [listError, setListError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [generateError, setGenerateError] = useState('');
  const generatingRef = useRef(false);
  const pendingPreferredIdRef = useRef('');
  const listRequestLifecycleRef = useRef(new RequestLifecycle());
  const detailRequestLifecycleRef = useRef(new RequestLifecycle());
  const generateRequestLifecycleRef = useRef(new RequestLifecycle());

  const loadBriefings = useCallback(async () => {
    const { sequence, signal } = listRequestLifecycleRef.current.start();
    setListLoading(true);
    setListError('');
    try {
      const payload = await fetchBriefingHistory({ apiFetch, signal });
      const nextItems = payload.items as BriefingListItem[];
      if (!listRequestLifecycleRef.current.isCurrent(sequence)) return;
      setItems(nextItems);
      setSelectedId((current) => {
        const selection = resolveBriefingLoadSelection({
          items: nextItems,
          currentId: current,
          pendingPreferredId: pendingPreferredIdRef.current,
          succeeded: true,
        });
        pendingPreferredIdRef.current = selection.pendingPreferredId;
        return selection.selectedId;
      });
    } catch (reason: any) {
      if (reason?.name === 'AbortError' || !listRequestLifecycleRef.current.isCurrent(sequence)) return;
      const selection = resolveBriefingLoadSelection({
        items: [],
        currentId: '',
        pendingPreferredId: pendingPreferredIdRef.current,
        succeeded: false,
      });
      pendingPreferredIdRef.current = selection.pendingPreferredId;
      setListError(reason?.message || '快报历史加载失败');
    } finally {
      if (listRequestLifecycleRef.current.isCurrent(sequence)) setListLoading(false);
    }
  }, []);

  const loadBriefingDetail = useCallback(async (briefingId: string) => {
    if (!briefingId) return;
    const { sequence, signal } = detailRequestLifecycleRef.current.start();
    setDetailLoading(true);
    setDetailError('');
    setDetail(null);
    try {
      const payload = await fetchBriefingDetail({ apiFetch, signal, briefingId });
      if (!detailRequestLifecycleRef.current.isCurrent(sequence) || payload?.id !== briefingId) return;
      setDetail(payload);
    } catch (reason: any) {
      if (reason?.name === 'AbortError' || !detailRequestLifecycleRef.current.isCurrent(sequence)) return;
      setDetailError(reason?.message || '快报详情加载失败');
    } finally {
      if (detailRequestLifecycleRef.current.isCurrent(sequence)) setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBriefings();
    return () => {
      listRequestLifecycleRef.current.abort();
      detailRequestLifecycleRef.current.abort();
      generateRequestLifecycleRef.current.abort();
    };
  }, [loadBriefings]);

  useEffect(() => {
    if (!selectedId) {
      detailRequestLifecycleRef.current.abort();
      setDetail(null);
      setDetailError('');
      setDetailLoading(false);
      return;
    }
    void loadBriefingDetail(selectedId);
    return () => detailRequestLifecycleRef.current.abort();
  }, [loadBriefingDetail, selectedId]);

  const handleGenerate = useCallback(async () => {
    if (generating) return;
    if (generatingRef.current) return;
    generatingRef.current = true;
    setGenerating(true);
    setGenerateError('');
    const { sequence, signal } = generateRequestLifecycleRef.current.start();
    try {
      const generated = await generateQuickBriefing({ apiFetch, signal });
      if (!generateRequestLifecycleRef.current.isCurrent(sequence)) return;
      pendingPreferredIdRef.current = generated.id;
      await loadBriefings();
    } catch (reason: any) {
      if (reason?.name === 'AbortError' || !generateRequestLifecycleRef.current.isCurrent(sequence)) return;
      setGenerateError(reason?.message || '即时快报生成失败');
    } finally {
      generatingRef.current = false;
      if (generateRequestLifecycleRef.current.isCurrent(sequence)) setGenerating(false);
    }
  }, [generating, loadBriefings]);

  const metrics = briefingMetrics(detail);
  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );

  return (
    <KiNavigationShell className="ki-shell-ingest-preview ki-shell-briefings" sceneVariant="ingest" laserPrimary>
      <section className="ki-shell-content" aria-label="即时快报工作区">
        <div className="ki-shell-legacy-ingest">
          <div className="legacy-ingest-root is-shell-embedded cinematic-ingest briefing-embedded-root flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
            <div className="flex-1 overflow-hidden px-4 md:px-8 pb-4 md:pb-8">
              <div className="max-w-[1500px] mx-auto pt-4 h-full">
                <div className="ki-ingest-split-stage briefing-split-stage">
                  <section className="ki-ingest-list-pane briefing-history-pane" aria-label="快报历史">
                    <header className="briefing-history-head">
                      <div>
                        <span>BRIEFING HISTORY</span>
                        <strong>快报历史</strong>
                      </div>
                      <button
                        type="button"
                        className="briefing-generate-button"
                        aria-label="生成即时快报"
                        title="生成即时快报"
                        disabled={generating}
                        onClick={handleGenerate}
                      >
                        {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                      </button>
                    </header>

                    {generateError && (
                      <div className="briefing-generate-error" role="alert">
                        <span>{generateError}</span>
                        <button type="button" onClick={handleGenerate}>重试</button>
                      </div>
                    )}

                    <div className="ki-ingest-event-list briefing-history-list" aria-live="polite">
                      {items.map((item) => (
                        <SpotlightListRow key={item.id} active={item.id === selectedId} spotlightColor="rgba(251, 113, 133, 0.18)">
                          <button type="button" className="ki-ingest-list-row briefing-history-row" aria-pressed={item.id === selectedId} onClick={() => setSelectedId(item.id)}>
                            <span className="ki-ingest-list-topic is-rose">
                              <span className="ki-ingest-list-type-icon">{item.type === 'daily' ? <FileText size={14} /> : <Zap size={14} />}</span>
                              <em>{typeLabel(item.type)}</em>
                            </span>
                            <strong>{formatTimeBeijing(item.created_at)}</strong>
                            <small className="ki-ingest-list-meta">{item.events_used} 条事件 · {item.topic_count} 个主题</small>
                          </button>
                        </SpotlightListRow>
                      ))}
                      {listLoading && <p className="ki-ingest-pane-state"><Loader2 size={15} className="animate-spin" />快报历史加载中</p>}
                      {!listLoading && listError && <p className="ki-ingest-pane-state is-error">{listError}<button type="button" onClick={() => void loadBriefings()}>重试</button></p>}
                      {!listLoading && !listError && items.length === 0 && <p className="ki-ingest-pane-state">暂无快报，生成一份即时快报开始整理</p>}
                    </div>
                  </section>

                  <section className="ki-ingest-detail-pane briefing-detail-pane" aria-label="快报详情">
                    <div className="briefing-detail-surface">
                      {detailLoading && <div className="briefing-detail-state"><Loader2 size={20} className="animate-spin" /><span>快报详情加载中</span></div>}
                      {!detailLoading && detailError && (
                        <div className="briefing-detail-state is-error" role="alert">
                          <span>{detailError}</span>
                          <button type="button" onClick={() => void loadBriefingDetail(selectedId)}>重试</button>
                        </div>
                      )}
                      {!detailLoading && !detailError && !detail && <div className="briefing-detail-state">选择一份快报查看详情</div>}
                      {!detailLoading && !detailError && detail && (
                        <>
                          <header className="briefing-detail-header">
                            <div>
                              <span>{detail.type === 'daily' ? 'DAILY INTELLIGENCE' : 'INSTANT INTELLIGENCE'}</span>
                              <h1>{typeLabel(detail.type)}</h1>
                            </div>
                            <time><Clock3 size={13} />{formatTimeBeijing(detail.created_at || selectedItem?.created_at || '')}</time>
                          </header>

                          <div className="briefing-topic-stream">
                            {detail.topics.map((topic, topicIndex) => (
                              <article className="briefing-topic-section" key={`${topic.topic}-${topicIndex}`}>
                                <header>
                                  <span>{String(topicIndex + 1).padStart(2, '0')}</span>
                                  <h2>{topic.topic_label || topic.topic || '未分类主题'}</h2>
                                </header>
                                {topic.summary && <p className="briefing-topic-summary">{topic.summary}</p>}
                                <div className="briefing-event-references">
                                  {topic.events.map((event) => (
                                    <button type="button" key={event.event_id} onClick={() => navigate(`/events/${event.event_id}`)}>
                                      <span>
                                        <strong>{event.title_cn || event.highlight || '查看关联事件'}</strong>
                                        {event.highlight && event.title_cn && <small>{event.highlight}</small>}
                                      </span>
                                      <em>{event.source_name || '关联事件'}<ExternalLink size={12} /></em>
                                    </button>
                                  ))}
                                  {topic.events.length === 0 && <p>该主题暂无关联事件</p>}
                                </div>
                              </article>
                            ))}
                            {detail.topics.length === 0 && <div className="briefing-detail-state">这份快报暂无主题内容</div>}
                          </div>

                          <footer className="briefing-status-box" aria-label="快报状态">
                            <span><b>{metrics.typeLabel}</b><small>类型</small></span>
                            <span><b>{formatTimeBeijing(metrics.generatedAt)}</b><small>生成时间</small></span>
                            <span><b>{metrics.topicCount}</b><small>主题</small></span>
                            <span><b>{metrics.eventCount}</b><small>事件</small></span>
                          </footer>
                        </>
                      )}
                    </div>
                  </section>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </KiNavigationShell>
  );
}
