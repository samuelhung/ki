import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bell, GitBranch, GitMerge, Lightbulb, Loader2, Plus, RefreshCw, ScanSearch, Search, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api';
import {
  buildChainGroups,
  filterChainGroups,
  getChainStats,
  getPendingReviewCount,
  resolveSelectedChain,
  summarizeChainNodeTypes,
} from '../components/cinematic-chains/chainWorkspace.mjs';
import { createChainDetailCache } from '../components/cinematic-chains/chainDetailCache.mjs';
import { RequestLifecycle } from '../components/ingest/requestLifecycle';
import SpotlightListRow from '../components/react-bits/SpotlightListRow';
import { ChainDetailModal as LegacyChainDetail } from '../components/cinematic-chains/ChainDetailView';
import { EditModal } from '../components/cinematic-chains/ChainEditorDialog';
import { HintsReviewModal } from '../components/cinematic-chains/ChainReviewDialogs';
import type { ChainHint, ChainNode, ChainSuggestion } from '../components/cinematic-chains/chainTypes';
import KiNavigationShell from './KiNavigationShell';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-chains/cinematic-chains.css';

type ChainMeta = { chain: string; icon?: string; flow_summary?: string };
type ChainOverlap = {
  chain_a: string;
  chain_b: string;
  overlap_score: number;
  reason?: string;
  fuzzy_shared?: string[];
};
type ChainMergeResult = {
  target_chain: string;
  node_count: number;
  flow?: Array<{ name: string; type: string }>;
};
type OperationStatus = { kind: 'success' | 'error'; message: string } | null;

export default function CinematicIndustryChains() {
  const navigate = useNavigate();
  const [nodes, setNodes] = useState<ChainNode[]>([]);
  const [metas, setMetas] = useState<ChainMeta[]>([]);
  const [hints, setHints] = useState<ChainHint[]>([]);
  const [suggestions, setSuggestions] = useState<ChainSuggestion[]>([]);
  const [hintCount, setHintCount] = useState(0);
  const [suggestionCount, setSuggestionCount] = useState(0);
  const [selectedName, setSelectedName] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [editNode, setEditNode] = useState<ChainNode | null>(null);
  const [hintsOpen, setHintsOpen] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [overlapOpen, setOverlapOpen] = useState(false);
  const [overlaps, setOverlaps] = useState<ChainOverlap[]>([]);
  const [checkingOverlap, setCheckingOverlap] = useState(false);
  const [overlapError, setOverlapError] = useState('');
  const [mergingOverlap, setMergingOverlap] = useState('');
  const [mergedFlow, setMergedFlow] = useState<ChainMergeResult | null>(null);
  const [reviewLoading, setReviewLoading] = useState<'hints' | 'suggestions' | ''>('');
  const [operationStatus, setOperationStatus] = useState<OperationStatus>(null);
  const coreLifecycleRef = useRef(new RequestLifecycle());
  const reviewCountLifecycleRef = useRef(new RequestLifecycle());
  const hintLifecycleRef = useRef(new RequestLifecycle());
  const suggestionLifecycleRef = useRef(new RequestLifecycle());
  const nodeCollectionLifecycleRef = useRef(new RequestLifecycle());
  const chainCollectionLifecycleRef = useRef(new RequestLifecycle());
  const detailCacheRef = useRef(createChainDetailCache());

  const loadCoreData = useCallback(async () => {
    const request = coreLifecycleRef.current.start();
    setLoading(true);
    try {
      const responses = await Promise.all([
        apiFetch('/api/chains/nodes', { signal: request.signal }),
        apiFetch('/api/chains', { signal: request.signal }),
      ]);
      const failedResponse = responses.find((response) => !response.ok);
      if (failedResponse) throw new Error(`产业链加载失败：HTTP ${failedResponse.status}`);
      const [nodeResponse, chainResponse] = responses;
      const [nodeData, chainData] = await Promise.all([nodeResponse.json(), chainResponse.json()]);
      if (!coreLifecycleRef.current.isCurrent(request.sequence)) return;
      const nextNodes = nodeData.nodes || [];
      const nextGroups = buildChainGroups(nextNodes);
      setNodes(nextNodes);
      setMetas(chainData.chains || []);
      setSelectedName((current) => resolveSelectedChain(nextGroups, current));
      setError('');
    } catch (reason: any) {
      if (!coreLifecycleRef.current.isCurrent(request.sequence) || reason?.name === 'AbortError') return;
      setError(reason?.message || '产业链加载失败');
    } finally {
      if (coreLifecycleRef.current.isCurrent(request.sequence)) setLoading(false);
    }
  }, []);

  const loadReviewCounts = useCallback(async () => {
    const request = reviewCountLifecycleRef.current.start();
    try {
      const responses = await Promise.all([
        apiFetch('/api/chains/hints/count', { signal: request.signal }),
        apiFetch('/api/chains/suggestions/count', { signal: request.signal }),
      ]);
      const failedResponse = responses.find((response) => !response.ok);
      if (failedResponse) throw new Error(`待审计数加载失败：HTTP ${failedResponse.status}`);
      const [hintData, suggestionData] = await Promise.all(responses.map((response) => response.json()));
      if (!reviewCountLifecycleRef.current.isCurrent(request.sequence)) return;
      setHintCount(getPendingReviewCount(hintData));
      setSuggestionCount(getPendingReviewCount(suggestionData));
    } catch (reason: any) {
      if (reason?.name !== 'AbortError' && reviewCountLifecycleRef.current.isCurrent(request.sequence)) {
        setOperationStatus({ kind: 'error', message: reason?.message || '待审计数加载失败' });
      }
    }
  }, []);

  const loadHints = useCallback(async () => {
    const request = hintLifecycleRef.current.start();
    setReviewLoading('hints');
    try {
      const response = await apiFetch('/api/chains/hints?status=pending&limit=50', { signal: request.signal });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `更新提示加载失败：HTTP ${response.status}`);
      if (hintLifecycleRef.current.isCurrent(request.sequence)) setHints(data.hints || []);
    } catch (reason: any) {
      if (reason?.name !== 'AbortError' && hintLifecycleRef.current.isCurrent(request.sequence)) {
        setOperationStatus({ kind: 'error', message: reason?.message || '更新提示加载失败' });
      }
    } finally {
      if (hintLifecycleRef.current.isCurrent(request.sequence)) setReviewLoading('');
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    const request = suggestionLifecycleRef.current.start();
    setReviewLoading('suggestions');
    try {
      const response = await apiFetch('/api/chains/suggestions?status=pending', { signal: request.signal });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `新链建议加载失败：HTTP ${response.status}`);
      if (suggestionLifecycleRef.current.isCurrent(request.sequence)) setSuggestions(data.suggestions || []);
    } catch (reason: any) {
      if (reason?.name !== 'AbortError' && suggestionLifecycleRef.current.isCurrent(request.sequence)) {
        setOperationStatus({ kind: 'error', message: reason?.message || '新链建议加载失败' });
      }
    } finally {
      if (suggestionLifecycleRef.current.isCurrent(request.sequence)) setReviewLoading('');
    }
  }, []);

  useEffect(() => {
    void loadCoreData();
    void loadReviewCounts();
    return () => {
      coreLifecycleRef.current.abort();
      reviewCountLifecycleRef.current.abort();
      hintLifecycleRef.current.abort();
      suggestionLifecycleRef.current.abort();
      nodeCollectionLifecycleRef.current.abort();
      chainCollectionLifecycleRef.current.abort();
    };
  }, [loadCoreData, loadReviewCounts]);

  useEffect(() => {
    if (!operationStatus) return undefined;
    const timeout = window.setTimeout(() => setOperationStatus(null), 4200);
    return () => window.clearTimeout(timeout);
  }, [operationStatus]);

  const groups = useMemo(() => buildChainGroups(nodes), [nodes]);
  const filteredGroups = useMemo(() => filterChainGroups(groups, query), [groups, query]);
  const selected = useMemo(() => groups.find((group) => group.name === selectedName) || null, [groups, selectedName]);
  const selectedMeta = useMemo(() => metas.find((meta) => meta.chain === selected?.name), [metas, selected?.name]);
  const stats = useMemo(() => getChainStats(groups, hintCount, suggestionCount), [groups, hintCount, suggestionCount]);

  const collectNode = useCallback(async (nodeId: string) => {
    const request = nodeCollectionLifecycleRef.current.start();
    try {
      const response = await apiFetch('/api/chains/nodes/ai-collect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, use_web: true }), signal: request.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || `节点采集失败：HTTP ${response.status}`);
      if (!nodeCollectionLifecycleRef.current.isCurrent(request.sequence)) return;
      setOperationStatus({ kind: 'success', message: `${data.node_name || '节点'}采集完成${data.countries ? ` · ${data.countries} 个市场数据` : ''}` });
      await loadCoreData();
    } catch (reason: any) {
      if (reason?.name === 'AbortError') return;
      setOperationStatus({ kind: 'error', message: `节点采集失败：${reason?.message || '请稍后重试'}` });
    }
  }, [loadCoreData]);

  const collectChain = useCallback(async (chainName: string) => {
    const reference = groups.find((group) => group.name === chainName)?.nodes[0];
    if (!reference) return;
    const request = chainCollectionLifecycleRef.current.start();
    try {
      const response = await apiFetch('/api/chains/ai-collect-all', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: reference.id, use_web: true }), signal: request.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || `全链采集失败：HTTP ${response.status}`);
      if (!chainCollectionLifecycleRef.current.isCurrent(request.sequence)) return;
      setOperationStatus({ kind: 'success', message: `${chainName}采集完成 · 更新 ${data.collected || 0} 个节点` });
      await loadCoreData();
    } catch (reason: any) {
      if (reason?.name === 'AbortError') return;
      setOperationStatus({ kind: 'error', message: `全链采集失败：${reason?.message || '请稍后重试'}` });
    }
  }, [groups, loadCoreData]);

  const checkOverlaps = useCallback(async () => {
    setCheckingOverlap(true);
    setOverlapError('');
    try {
      const response = await apiFetch('/api/chains/overlap-check');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `重叠检测失败：HTTP ${response.status}`);
      setOverlaps(data.overlaps || []);
      setMergedFlow(null);
      setOverlapOpen(true);
    } catch (reason: any) {
      setOverlapError(reason?.message || '重叠检测失败');
      setOverlapOpen(true);
    } finally {
      setCheckingOverlap(false);
    }
  }, []);

  const mergeOverlap = useCallback(async (chainA: string, chainB: string, into: string) => {
    const key = `${chainA}|||${chainB}|||${into}`;
    setMergingOverlap(key);
    setOverlapError('');
    try {
      const response = await apiFetch('/api/chains/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chain_a: chainA, chain_b: chainB, into }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || '产业链合并失败');
      setMergedFlow(data);
      setOverlaps((current) => current.filter((item) => item.chain_a !== chainA || item.chain_b !== chainB));
      setOperationStatus({ kind: 'success', message: `${data.target_chain}合并完成 · ${data.node_count} 个节点` });
      await loadCoreData();
    } catch (reason: any) {
      setOverlapError(reason?.message || '产业链合并失败');
    } finally {
      setMergingOverlap('');
    }
  }, [loadCoreData]);

  const refreshAll = useCallback(() => {
    void loadCoreData();
    void loadReviewCounts();
  }, [loadCoreData, loadReviewCounts]);

  const openHints = useCallback(() => {
    setHintsOpen(true);
    void loadHints();
  }, [loadHints]);

  const openSuggestions = useCallback(() => {
    setSuggestionsOpen(true);
    void loadSuggestions();
  }, [loadSuggestions]);

  const chainActions = (
    <>
      <button type="button" onClick={() => { setEditNode(null); setEditorOpen(true); }} aria-label="新建产业链节点" title="新建产业链节点"><Plus size={14} /></button>
      <button type="button" onClick={openHints} disabled={hintCount === 0 || reviewLoading === 'hints'} aria-label="审核更新提示" title={`审核更新提示 · ${hintCount} 条`}>{reviewLoading === 'hints' ? <Loader2 className="animate-spin" size={14} /> : <Bell size={14} />}</button>
      <button type="button" onClick={openSuggestions} disabled={suggestionCount === 0 || reviewLoading === 'suggestions'} aria-label="审核新链建议" title={`审核新链建议 · ${suggestionCount} 条`}>{reviewLoading === 'suggestions' ? <Loader2 className="animate-spin" size={14} /> : <Lightbulb size={14} />}</button>
      <button type="button" onClick={() => void checkOverlaps()} disabled={checkingOverlap} aria-label="检测产业链重叠" title="检测产业链重叠">{checkingOverlap ? <Loader2 className="animate-spin" size={14} /> : <ScanSearch size={14} />}</button>
      <button type="button" onClick={refreshAll} aria-label="刷新产业链" title="刷新产业链"><RefreshCw size={14} /></button>
    </>
  );

  return (
    <KiNavigationShell
      className="ki-shell-ingest-preview ki-shell-chains"
      sceneVariant="ingest"
      laserPrimary
      topAccessory={(
        <label className="ki-ingest-list-search" aria-label="搜索产业链">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索产业链或节点" />
        </label>
      )}
    >
      <section className="ki-shell-content" aria-label="产业链工作区">
        <div className="ki-shell-legacy-ingest">
          <div className="legacy-ingest-root is-shell-embedded cinematic-ingest ki-chains-embedded-root flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
            <div className="flex-1 overflow-hidden px-4 md:px-8 pb-4 md:pb-8">
              <div className="max-w-[1500px] mx-auto pt-4 h-full">
                <div className="ki-ingest-split-stage">
                  <section className="ki-ingest-list-pane" aria-label="产业链列表">
                    <nav className="ingest-topic-orbit ki-ingest-topic-orbit chain-category-tabs" aria-label="产业链分类">
                      <button type="button" className="is-active is-gold"><GitBranch size={17} /><span>产业链</span></button>
                    </nav>
                    <div className="ki-ingest-event-list chain-index-list">
                      {filteredGroups.map((group) => (
                        <SpotlightListRow key={group.name} active={selectedName === group.name} spotlightColor="rgba(118, 230, 183, 0.16)">
                          <button type="button" className="ki-ingest-list-row chain-list-row" onClick={() => setSelectedName(group.name)}>
                            <span className="ki-ingest-list-topic is-cyan">
                              <span className="ki-ingest-list-type-icon"><GitBranch size={14} /></span>
                              <em>{group.nodes.length} 节点</em>
                            </span>
                            <strong>{group.name}</strong>
                            <small className="ki-ingest-list-meta">{summarizeChainNodeTypes(group.nodes) || '等待节点分类'}</small>
                          </button>
                        </SpotlightListRow>
                      ))}
                      {loading && groups.length === 0 && <div className="chain-list-state"><Loader2 className="animate-spin" size={17} /><span>产业链加载中</span></div>}
                      {!loading && filteredGroups.length === 0 && <div className="chain-list-state"><span>{query ? '没有匹配产业链' : error || '暂无产业链'}</span></div>}
                      {error && groups.length > 0 && <div className="chain-list-warning">{error}</div>}
                    </div>
                    <footer className="chain-list-summary"><span>{stats.chains} 条产业链</span><span>{stats.nodes} 个节点</span><span>{stats.hints + stats.suggestions} 条待审</span></footer>
                  </section>

                  <section className="ki-ingest-detail-pane chain-detail-pane" aria-label={selected?.name || '产业链详情'}>
                    {selected ? (
                      <LegacyChainDetail
                        embedded
                        chainName={selected.name}
                        chainIcon={selectedMeta?.icon}
                        chainFlowSummary={selectedMeta?.flow_summary || ''}
                        nodes={selected.nodes}
                        allNodes={nodes}
                        onCollectNode={collectNode}
                        onCollectChain={collectChain}
                        onEditNode={(node) => { setEditNode(node); setEditorOpen(true); }}
                        onSaved={loadCoreData}
                        embeddedActions={chainActions}
                        detailCache={detailCacheRef.current}
                      />
                    ) : (
                      <div className="chain-empty-detail">
                        <div className="chain-empty-detail-actions">{chainActions}</div>
                        <div className="chain-cinematic-loading">{loading ? <Loader2 className="animate-spin" /> : error || '暂无产业链'}</div>
                      </div>
                    )}
                  </section>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {operationStatus && <div className={`chain-operation-status is-${operationStatus.kind}`} role="status">{operationStatus.message}</div>}

      {editorOpen && <EditModal key={editNode?.id || 'new'} node={editNode} allNodes={nodes} defaultChain={selected?.name} onClose={() => setEditorOpen(false)} onSaved={() => { setEditorOpen(false); void loadCoreData(); }} />}
      {hintsOpen && <HintsReviewModal hints={hints} onClose={() => setHintsOpen(false)} onResolved={() => { setHintsOpen(false); void loadCoreData(); void loadReviewCounts(); }} />}
      {suggestionsOpen && <SuggestionDialog suggestions={suggestions} onClose={() => setSuggestionsOpen(false)} onChanged={async (id, action) => {
        setSuggestions((current) => current.filter((item) => item.id !== id));
        setSuggestionCount((current) => Math.max(0, current - 1));
        if (action === 'adopt') await loadCoreData();
        void loadReviewCounts();
      }} />}
      {overlapOpen && (
        <OverlapDialog
          overlaps={overlaps}
          error={overlapError}
          busyKey={mergingOverlap}
          mergedFlow={mergedFlow}
          onClose={() => setOverlapOpen(false)}
          onMerge={mergeOverlap}
        />
      )}
    </KiNavigationShell>
  );
}

function OverlapDialog({ overlaps, error, busyKey, mergedFlow, onClose, onMerge }: {
  overlaps: ChainOverlap[];
  error: string;
  busyKey: string;
  mergedFlow: ChainMergeResult | null;
  onClose: () => void;
  onMerge: (chainA: string, chainB: string, into: string) => void;
}) {
  const [newNames, setNewNames] = useState<Record<string, string>>({});
  const [mergeConfirmation, setMergeConfirmation] = useState<{
    chainA: string;
    chainB: string;
    into: string;
    targetLabel: string;
    overlapScore: number;
    sharedNodes: string[];
  } | null>(null);

  const requestMergeConfirmation = (item: ChainOverlap, into: string, targetLabel: string) => {
    const sharedNodes = item.fuzzy_shared || [];
    setMergeConfirmation({
      chainA: item.chain_a,
      chainB: item.chain_b,
      into,
      targetLabel,
      overlapScore: item.overlap_score || 0,
      sharedNodes,
    });
  };

  const confirmMerge = () => {
    if (!mergeConfirmation) return;
    const { chainA, chainB, into } = mergeConfirmation;
    setMergeConfirmation(null);
    onMerge(chainA, chainB, into);
  };

  return (
    <div className="chain-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="chain-suggestion-dialog chain-overlap-dialog">
        <button type="button" aria-label="关闭" onClick={onClose}><X /></button>
        <header><span>CHAIN OVERLAP</span><h2>产业链重叠检测</h2></header>
        <div>
          {error && <p className="chain-overlap-error">{error}</p>}
          {mergedFlow && (
            <section className="chain-merge-result">
              <b>「{mergedFlow.target_chain}」合并完成 · {mergedFlow.node_count} 个节点</b>
              <div>{mergedFlow.flow?.map((item, index) => <span key={`${item.name}-${index}`}>{index > 0 && <i>→</i>}{item.name}<small>{item.type}</small></span>)}</div>
            </section>
          )}
          {mergeConfirmation && (
            <section className="chain-merge-confirmation" aria-label="产业链合并确认">
              <span>MERGE PREVIEW</span>
              <h3>确认合并到「{mergeConfirmation.targetLabel}」？</h3>
              <p>{mergeConfirmation.chainA} 与 {mergeConfirmation.chainB} 的重叠度为 {Math.round(mergeConfirmation.overlapScore * 100)}%。合并会移动节点并删除被并入的旧链，操作不可撤销。</p>
              {mergeConfirmation.sharedNodes.length > 0 && <div>{mergeConfirmation.sharedNodes.map((node) => <em key={node}>{node}</em>)}</div>}
              <footer>
                <button type="button" onClick={() => setMergeConfirmation(null)}>取消</button>
                <button type="button" disabled={Boolean(busyKey)} onClick={confirmMerge}>确认合并</button>
              </footer>
            </section>
          )}
          {!error && overlaps.length === 0 && !mergedFlow && <p>未检测到产业链重叠</p>}
          {overlaps.map((item) => {
            const pairKey = `${item.chain_a}|||${item.chain_b}`;
            const newName = newNames[pairKey] || '';
            return (
              <article key={pairKey} className="chain-overlap-item">
                <div className="chain-overlap-heading">
                  <h3>{item.chain_a}<GitMerge size={13} />{item.chain_b}</h3>
                  <small>重叠度 {Math.round((item.overlap_score || 0) * 100)}%</small>
                </div>
                {item.reason && <p>{item.reason}</p>}
                {item.fuzzy_shared?.length ? <div className="chain-overlap-shared">{item.fuzzy_shared.map((label) => <span key={label}>{label}</span>)}</div> : null}
                <footer>
                  <button disabled={Boolean(busyKey)} onClick={() => requestMergeConfirmation(item, 'a', item.chain_a)}>并入 {item.chain_a}</button>
                  <button disabled={Boolean(busyKey)} onClick={() => requestMergeConfirmation(item, 'b', item.chain_b)}>并入 {item.chain_b}</button>
                  <label>
                    <input value={newName} onChange={(event) => setNewNames((current) => ({ ...current, [pairKey]: event.target.value }))} placeholder="新链名称" />
                    <button disabled={Boolean(busyKey) || !newName.trim()} onClick={() => requestMergeConfirmation(item, `new:${newName.trim()}`, newName.trim())}>{busyKey === `${pairKey}|||new:${newName.trim()}` ? <Loader2 className="animate-spin" size={11} /> : null}合并为新链</button>
                  </label>
                </footer>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function SuggestionDialog({ suggestions, onClose, onChanged }: { suggestions: ChainSuggestion[]; onClose: () => void; onChanged: (id: string, action: 'adopt' | 'dismiss') => void | Promise<void> }) {
  const [busy, setBusy] = useState('');
  const [actionError, setActionError] = useState('');
  async function act(id: string, action: 'adopt' | 'dismiss') {
    setBusy(id);
    setActionError('');
    try {
      const response = await apiFetch(`/api/chains/suggestions/${id}/${action}`, { method: 'POST' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `处理失败：HTTP ${response.status}`);
      await onChanged(id, action);
    } catch (reason: any) {
      setActionError(reason?.message || '建议处理失败');
    } finally {
      setBusy('');
    }
  }
  return (
    <div className="chain-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="chain-suggestion-dialog">
        <button type="button" aria-label="关闭" onClick={onClose}><X /></button>
        <header><span>CHAIN DISCOVERY</span><h2>新产业链建议</h2></header>
        <div>
          {actionError && <p className="chain-overlap-error">{actionError}</p>}
          {suggestions.length === 0 ? <p>暂无待处理建议</p> : suggestions.map((item) => (
            <article key={item.id}>
              <div className="chain-suggestion-heading">
                <div>
                  <h3>{item.chain_name}</h3>
                  <p>{item.reason || '由采集内容识别出的新产业链候选'}</p>
                </div>
                <small>置信度 {Math.round((item.confidence || 0) * 100)}%</small>
              </div>
              {item.source_quote && <blockquote>{item.source_quote}</blockquote>}
              <div className="chain-suggestion-nodes">
                {item.nodes_json.map((node, index) => (
                  <div key={`${node.name || 'node'}-${index}`}>
                    <header><b>{node.name || '未命名节点'}</b><span>{node.node_type || '待分类'}</span></header>
                    {node.description && <p>{node.description}</p>}
                    {node.initial_data && <small>{node.initial_data}</small>}
                  </div>
                ))}
              </div>
              <footer>
                <button disabled={busy === item.id} onClick={() => act(item.id, 'dismiss')}>忽略</button>
                <button disabled={busy === item.id} onClick={() => act(item.id, 'adopt')}>采纳</button>
              </footer>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
