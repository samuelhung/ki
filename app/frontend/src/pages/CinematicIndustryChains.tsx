import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { Bell, GitBranch, GitMerge, Lightbulb, Loader2, Plus, RefreshCw, Search, X } from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import { apiFetch } from '../api';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import { buildChainGroups, filterChainGroups, getChainStats } from '../components/cinematic-chains/chainWorkspace.mjs';
import LaserFlow from '../components/react-bits/LaserFlow';
import { ChainDetailModal as LegacyChainDetail, EditModal, HintsReviewModal, type ChainHint, type ChainNode, type ChainSuggestion } from './IndustryChains';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-chains/cinematic-chains.css';

type ChainMeta = { chain: string; icon?: string; flow_summary?: string };

export default function CinematicIndustryChains() {
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [nodes, setNodes] = useState<ChainNode[]>([]);
  const [metas, setMetas] = useState<ChainMeta[]>([]);
  const [hints, setHints] = useState<ChainHint[]>([]);
  const [suggestions, setSuggestions] = useState<ChainSuggestion[]>([]);
  const [selectedName, setSelectedName] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [editNode, setEditNode] = useState<ChainNode | null>(null);
  const [hintsOpen, setHintsOpen] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [collecting, setCollecting] = useState('');

  async function loadData() {
    setLoading(true);
    try {
      const [nodeResponse, chainResponse, hintResponse, suggestionResponse] = await Promise.all([
        apiFetch('/api/chains/nodes'), apiFetch('/api/chains'),
        apiFetch('/api/chains/hints?status=pending&limit=50'), apiFetch('/api/chains/suggestions?status=pending'),
      ]);
      const [nodeData, chainData, hintData, suggestionData] = await Promise.all([
        nodeResponse.json(), chainResponse.json(), hintResponse.json(), suggestionResponse.json(),
      ]);
      const nextNodes = nodeData.nodes || [];
      const names = new Set(nextNodes.map((node: ChainNode) => node.chain));
      setNodes(nextNodes); setMetas(chainData.chains || []); setHints(hintData.hints || []); setSuggestions(suggestionData.suggestions || []);
      setSelectedName((current) => current && names.has(current) ? current : nextNodes[0]?.chain || '');
      setError('');
    } catch (reason: any) { setError(reason?.message || '产业链加载失败'); }
    setLoading(false);
  }

  useEffect(() => { loadData(); }, []);

  const groups = useMemo(() => buildChainGroups(nodes), [nodes]);
  const filteredGroups = useMemo(() => filterChainGroups(groups, query), [groups, query]);
  const selected = groups.find((group) => group.name === selectedName) || filteredGroups[0];
  const selectedMeta = metas.find((meta) => meta.chain === selected?.name);
  const stats = useMemo(() => getChainStats(groups, hints.length, suggestions.length), [groups, hints.length, suggestions.length]);
  const typeCount = selected?.nodes.reduce((result: Record<string, number>, node: ChainNode) => ({ ...result, [node.node_type]: (result[node.node_type] || 0) + 1 }), {}) || {};
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  async function collectNode(nodeId: string) {
    setCollecting(nodeId);
    try { await apiFetch('/api/chains/nodes/ai-collect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ node_id: nodeId, use_web: true }) }); await loadData(); }
    finally { setCollecting(''); }
  }

  async function collectChain(chainName: string) {
    const reference = selected?.nodes[0]; if (!reference) return;
    setCollecting(chainName);
    try { await apiFetch('/api/chains/ai-collect-all', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ node_id: reference.id, use_web: true }) }); await loadData(); }
    finally { setCollecting(''); }
  }

  const status = <section className="ingest-observation cinematic-observation chain-status"><div className="panel-status"><i className="signal-dot" /><span>产业链底座</span></div><span>节点关系、全球份额与供应链风险统一维护</span><div className="system-status-summary"><span className="is-good">产业链 {stats.chains}</span><span className="is-cyan">节点 {stats.nodes}</span><span className="is-warn">待审核 {stats.hints + stats.suggestions}</span></div><div className="panel-detail-grid"><span>当前<b>{selected?.name || '--'}</b></span><span>结构<b>{selected?.nodes.length || 0} 节点</b></span></div></section>;
  const commands = <section className="ingest-command-launcher chain-command-launcher"><div className="launcher-actions"><button className="launcher-action ingest-command-metric is-douyin" onClick={() => { setEditNode(null); setEditorOpen(true); }}><Plus size={15} /><b>新建节点</b><span>补充结构</span><small>CREATE</small></button><button className="launcher-action ingest-command-metric is-file" onClick={() => setHintsOpen(true)}><Bell size={15} /><b>更新提示</b><span>{hints.length} 条</span><small>REVIEW</small></button><button className="launcher-action ingest-command-metric is-concept" onClick={() => setSuggestionsOpen(true)}><Lightbulb size={15} /><b>新链建议</b><span>{suggestions.length} 条</span><small>SUGGEST</small></button><button className="launcher-action ingest-command-metric is-source" onClick={loadData}><RefreshCw size={15} /><b>刷新数据</b><span>{stats.nodes} 节点</span><small>REFRESH</small></button></div></section>;
  const index = <><div className="ingest-topic-orbit chain-topic-orbit"><button className="is-active is-gold"><GitBranch size={14} /><span>产业链</span></button><button onClick={() => navigateWithCurtain('/industry-flow')}><GitMerge size={14} /><span>全景</span></button></div><label className="chain-index-search"><Search size={13} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索产业链或节点" /></label><div className="ingest-index-list chain-index-list">{filteredGroups.map((group, index) => <button key={group.name} className={`ingest-index-item${selected?.name === group.name ? ' is-active' : ''}`} style={{ '--index-depth-scale': 1 - Math.min(index, 9) * .028, '--index-depth-z': `${-Math.min(index, 9) * 3}px`, '--index-depth-opacity': 1 - Math.min(index, 9) * .04 } as CSSProperties} onClick={() => setSelectedName(group.name)}><div className="index-title"><b>{group.name}</b><span><em className="is-cyan">{group.nodes.length} 节点</em></span></div><small>{[...new Set(group.nodes.map((node: ChainNode) => node.node_type))].join(' · ')}</small></button>)}</div></>;

  return <CinematicTemplatePage className="cinematic-chains" profile={profile} topic="gold" style={style} variant="system" status={status} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="产业链工作舱" indexAriaLabel="产业链索引" index={index} stageAriaLabel="产业链详情" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} color="#76E6B7" verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} />{selected ? <LegacyChainDetail embedded chainName={selected.name} chainIcon={selectedMeta?.icon} chainFlowSummary={selectedMeta?.flow_summary || ''} nodes={selected.nodes} allNodes={nodes} onCollectNode={collectNode} onCollectChain={collectChain} onEditNode={(node) => { setEditNode(node); setEditorOpen(true); }} onSaved={loadData} /> : <div className="chain-cinematic-loading">{loading ? <Loader2 className="animate-spin" /> : error || '暂无产业链'}</div>}<div className="laser-media-box chain-core-box"><span>INDUSTRY CHAIN</span><b>{selected?.name || '等待产业链'}</b><div><em>原材料<strong>{typeCount['原材料'] || 0}</strong></em><em>中间品<strong>{typeCount['中间品'] || 0}</strong></em><em>零部件<strong>{typeCount['零部件'] || 0}</strong></em><em>终端<strong>{typeCount['终端'] || 0}</strong></em></div></div></>} />} overlays={<>{editorOpen && <EditModal key={editNode?.id || 'new'} node={editNode} allNodes={nodes} defaultChain={selected?.name} onClose={() => setEditorOpen(false)} onSaved={() => { setEditorOpen(false); loadData(); }} />}{hintsOpen && <HintsReviewModal hints={hints} onClose={() => setHintsOpen(false)} onResolved={() => { setHintsOpen(false); loadData(); }} />}{suggestionsOpen && <SuggestionDialog suggestions={suggestions} onClose={() => setSuggestionsOpen(false)} onChanged={loadData} />}</>} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}

function SuggestionDialog({ suggestions, onClose, onChanged }: { suggestions: ChainSuggestion[]; onClose: () => void; onChanged: () => void }) {
  const [busy, setBusy] = useState('');
  async function act(id: string, action: 'adopt' | 'dismiss') { setBusy(id); await apiFetch(`/api/chains/suggestions/${id}/${action}`, { method: 'POST' }); await onChanged(); setBusy(''); }
  return <div className="chain-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="chain-suggestion-dialog"><button onClick={onClose}><X /></button><header><span>CHAIN DISCOVERY</span><h2>新产业链建议</h2></header><div>{suggestions.length === 0 ? <p>暂无待处理建议</p> : suggestions.map((item) => <article key={item.id}><h3>{item.chain_name}</h3><p>{item.reason || item.source_quote || '由采集内容识别出的新产业链候选'}</p><small>置信度 {Math.round((item.confidence || 0) * 100)}%</small><footer><button disabled={busy === item.id} onClick={() => act(item.id, 'dismiss')}>忽略</button><button disabled={busy === item.id} onClick={() => act(item.id, 'adopt')}>采纳</button></footer></article>)}</div></section></div>;
}
