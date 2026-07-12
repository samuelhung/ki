import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { ArrowLeft, ExternalLink, Layers, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import { apiFetch } from '../api';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import LaserFlow from '../components/react-bits/LaserFlow';
import SeriesDetail from './SeriesDetail';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-series/cinematic-series.css';
import '../components/cinematic-series/cinematic-series-detail.css';

type Member = { id: string; title: string; overview?: string; topic?: string; source_id?: string };
type Detail = { id: string; name: string; description?: string; status: string; created_at: string; updated_at?: string; intro?: string; summary?: string; paper?: string; members?: Member[] };

export default function CinematicSeriesDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const response = await apiFetch(`/api/ingest/series/${id}`);
      if (!response.ok) throw new Error('专题不存在');
      setDetail(await response.json()); setError('');
    } catch (reason: any) { setError(reason?.message || '专题加载失败'); }
    setLoading(false);
  }
  useEffect(() => { load(); }, [id]);

  const members = detail?.members || [];
  const generated = useMemo(() => [detail?.intro, detail?.summary, detail?.paper].filter(Boolean).length, [detail]);
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  const status = <section className="ingest-observation cinematic-observation series-detail-status" aria-label="专题详情状态"><div className="panel-status"><i className="signal-dot" /><span>专题展厅</span></div><span>{detail?.description || '读取专题脉络与成员内容'}</span><div className="system-status-summary"><span className="is-good">{detail?.status || '--'}</span><span className="is-cyan">成员 {members.length}</span><span className="is-warn">AI 产物 {generated}/3</span></div><div className="panel-detail-grid"><span>当前<b>{detail?.name || '--'}</b></span><span>更新<b>{detail?.updated_at?.slice(0, 10) || detail?.created_at?.slice(0, 10) || '--'}</b></span></div></section>;
  const commands = <section className="ingest-command-launcher series-detail-command-launcher" aria-label="专题导航"><div className="launcher-actions"><button className="launcher-action ingest-command-metric is-douyin" onClick={() => navigateWithCurtain('/series')}><ArrowLeft size={15} /><b>返回专题</b><span>专题列表</span><small>BACK</small></button><button className="launcher-action ingest-command-metric is-file" onClick={load}><RefreshCw size={15} /><b>刷新详情</b><span>{members.length} 条</span><small>REFRESH</small></button><button className="launcher-action ingest-command-metric is-concept" onClick={() => navigateWithCurtain(`/series-old/${id}`)}><Layers size={15} /><b>旧版对比</b><span>验收入口</span><small>LEGACY</small></button></div></section>;
  const index = <><div className="ingest-topic-orbit series-detail-topic-orbit"><button className="is-active is-gold"><Layers size={14} /><span>成员</span></button></div><div className="ingest-index-list series-detail-member-index">{members.map((member, index) => <button key={member.id} className="ingest-index-item" style={{ '--index-depth-scale': 1 - Math.min(index, 9) * .026, '--index-depth-z': `${-Math.min(index, 9) * 3}px`, '--index-depth-opacity': 1 - Math.min(index, 9) * .05 } as CSSProperties} onClick={() => navigateWithCurtain(`/events/${member.id}`)}><div className="index-title"><b>{member.title}</b><span><em className="is-cyan">{String(index + 1).padStart(2, '0')}</em></span></div><small>{member.topic || '未分类'} · {member.overview || '进入内容详情'}</small></button>)}</div></>;

  return <CinematicTemplatePage className="cinematic-series-detail" profile={profile} topic="violet" style={style} variant="system" status={status} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="专题详情舱" indexAriaLabel="专题成员" index={index} stageAriaLabel="专题详情正文" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} />{loading ? <div className="series-cinematic-loading"><Loader2 className="animate-spin" /></div> : error ? <div className="series-cinematic-loading is-error">{error}</div> : <SeriesDetail embedded />}<div className="laser-media-box series-detail-core-box"><span>SERIES EXHIBITION</span><b>{detail?.name || '专题加载中'}</b><div><em>成员<strong>{members.length} 条</strong></em><em>AI 产物<strong>{generated} / 3</strong></em><button onClick={() => members[0] && navigateWithCurtain(`/events/${members[0].id}`)} disabled={!members.length}>首篇内容 <ExternalLink size={13} /></button></div></div></>} />} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}
