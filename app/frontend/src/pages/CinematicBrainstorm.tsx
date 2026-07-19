import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Brain, Coins, Globe, Lightbulb, Loader2, RefreshCw, Search, Telescope, Trash2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiFetch } from '../api';
import {
  filterBrainstormQuestions,
  getBrainstormStats,
  linkedEventCount,
  removeBrainstormQuestion,
  resolveBrainstormSelection,
} from '../components/cinematic-brainstorm/brainstormWorkspace.mjs';
import SpotlightListRow from '../components/react-bits/SpotlightListRow';
import type { BrainstormQuestion } from './BrainstormDetailPage';
import KiNavigationShell from './KiNavigationShell';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-brainstorm/cinematic-brainstorm.css';

const LegacyBrainstormDetail = lazy(() => import('./BrainstormDetailPage'));

const TOPICS = [
  { key: '全部', icon: Lightbulb, accent: 'gold' },
  { key: '格局', icon: Globe, accent: 'blue' },
  { key: '财富', icon: Coins, accent: 'gold' },
  { key: '认知', icon: Brain, accent: 'violet' },
  { key: '前瞻', icon: Telescope, accent: 'cyan' },
] as const;

type TopicKey = (typeof TOPICS)[number]['key'];

function topicAccent(topic?: string) {
  return TOPICS.find((item) => item.key === topic)?.accent || 'violet';
}

export default function CinematicBrainstorm() {
  const navigate = useNavigate();
  const { id: routeId = '' } = useParams<{ id?: string }>();
  const [items, setItems] = useState<BrainstormQuestion[]>([]);
  const [selectedId, setSelectedId] = useState(routeId);
  const [topic, setTopic] = useState<TopicKey>('全部');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadData = useCallback(async (preferredId = '') => {
    setLoading(true);
    try {
      const response = await apiFetch('/api/brainstorm?limit=200');
      if (!response.ok) throw new Error('脑暴问题加载失败');
      const data = await response.json();
      const next = data.questions || [];
      setItems(next);
      setSelectedId((current) => resolveBrainstormSelection(next, preferredId, current));
      setError('');
    } catch (reason: any) {
      setError(reason?.message || '脑暴问题加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(routeId); }, [loadData]);

  useEffect(() => {
    if (items.length === 0) return;
    const resolvedId = resolveBrainstormSelection(items, routeId, selectedId);
    if (resolvedId !== selectedId) setSelectedId(resolvedId);
    if (resolvedId && routeId !== resolvedId) {
      navigate(`/brainstorm/${resolvedId}`, { replace: !routeId });
    }
  }, [items, navigate, routeId, selectedId]);

  const filtered = useMemo(
    () => filterBrainstormQuestions(items, topic, query),
    [items, query, topic],
  );
  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );
  const stats = useMemo(() => getBrainstormStats(items), [items]);

  const handleSelect = useCallback((questionId: string) => {
    setSelectedId(questionId);
    navigate(`/brainstorm/${questionId}`);
  }, [navigate]);

  const handleTopicChange = useCallback((nextTopic: TopicKey) => {
    setTopic(nextTopic);
    const next = filterBrainstormQuestions(items, nextTopic, query)[0];
    if (next) handleSelect(next.id);
  }, [handleSelect, items, query]);

  const handleQuestionChange = useCallback((detail: BrainstormQuestion) => {
    setItems((current) => current.map((item) => item.id === detail.id ? { ...item, ...detail } : item));
  }, []);

  const deleteSelected = useCallback(async () => {
    if (!selected || !window.confirm(`确定删除「${selected.question}」？`)) return;
    const response = await apiFetch(`/api/brainstorm/${selected.id}`, { method: 'DELETE' });
    if (!response.ok) return;
    const next = removeBrainstormQuestion(items, selected.id);
    setItems(next.items);
    setSelectedId(next.selectedId);
    navigate(next.selectedId ? `/brainstorm/${next.selectedId}` : '/brainstorm', { replace: true });
  }, [items, navigate, selected]);

  return (
    <KiNavigationShell
      className="ki-shell-ingest-preview ki-shell-brainstorm"
      sceneVariant="ingest"
      laserPrimary
      topAccessory={(
        <label className="ki-ingest-list-search" aria-label="搜索头脑风暴问题">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索问题" />
        </label>
      )}
    >
      <section className="ki-shell-content" aria-label="头脑风暴工作区">
        <div className="ki-shell-legacy-ingest">
          <div className="legacy-ingest-root is-shell-embedded cinematic-ingest ki-brainstorm-embedded-root flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
            <div className="flex-1 overflow-hidden px-4 md:px-8 pb-4 md:pb-8">
              <div className="max-w-[1500px] mx-auto pt-4 h-full">
                <div className="ki-ingest-split-stage">
                  <section className="ki-ingest-list-pane" aria-label="脑暴问题列表">
                    <nav className="ingest-topic-orbit ki-ingest-topic-orbit brainstorm-topic-tabs" aria-label="脑暴问题分类">
                      {TOPICS.map(({ key, icon: Icon, accent }) => (
                        <button
                          key={key}
                          type="button"
                          className={`${topic === key ? 'is-active ' : ''}is-${accent}`}
                          onClick={() => handleTopicChange(key)}
                        >
                          <Icon size={17} />
                          <span>{key}</span>
                        </button>
                      ))}
                    </nav>

                    <div className="ki-ingest-event-list brainstorm-question-list" aria-live="polite">
                      {loading ? (
                        <div className="ki-ingest-pane-state"><Loader2 size={16} className="animate-spin" />加载问题</div>
                      ) : error ? (
                        <div className="ki-ingest-pane-state is-error"><span>{error}</span><button type="button" onClick={() => void loadData(routeId)}>重试</button></div>
                      ) : filtered.length === 0 ? (
                        <div className="ki-ingest-pane-state">{query ? '没有匹配的问题' : '暂无脑暴问题'}</div>
                      ) : filtered.map((item) => {
                        const accent = topicAccent(item.topic);
                        const Icon = TOPICS.find((entry) => entry.key === item.topic)?.icon || Brain;
                        return (
                          <SpotlightListRow
                            key={item.id}
                            active={selectedId === item.id}
                            spotlightColor="rgba(184, 145, 255, 0.2)"
                          >
                            <button type="button" className="ki-ingest-list-row brainstorm-question-row" onClick={() => handleSelect(item.id)}>
                              <span className={`ki-ingest-list-topic is-${accent}`}>
                                <span className="ki-ingest-list-type-icon"><Icon size={14} /></span>
                                <em>{item.topic || '认知'}</em>
                              </span>
                              <strong>{item.question}</strong>
                              <small className="ki-ingest-list-meta">{linkedEventCount(item)} 条资料 · {item.status === 'done' ? '已完成' : '进行中'}</small>
                            </button>
                          </SpotlightListRow>
                        );
                      })}
                    </div>
                  </section>

                  <section className="ki-ingest-detail-pane brainstorm-detail-pane" aria-label="脑暴问题详情">
                    <div className="brainstorm-detail-host">
                      {selected ? (
                        <Suspense fallback={<div className="ki-ingest-pane-state"><Loader2 size={16} className="animate-spin" />加载详情</div>}>
                          <LegacyBrainstormDetail
                            embedded
                            questionId={selected.id}
                            onQuestionChange={handleQuestionChange}
                            embeddedActions={(
                              <>
                                <button className="brainstorm-shell-action" type="button" onClick={() => void loadData(selectedId)} title="刷新问题" aria-label="刷新问题"><RefreshCw size={15} /></button>
                                <button className="brainstorm-shell-action is-delete" type="button" onClick={() => void deleteSelected()} title="删除当前问题" aria-label="删除当前问题"><Trash2 size={15} /></button>
                              </>
                            )}
                          />
                        </Suspense>
                      ) : (
                        <div className="ki-ingest-pane-state">选择一个问题开始思考</div>
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
