import { useCallback, useMemo, useState, type CSSProperties } from 'react';
import { ArrowLeft, FileText, Library, RefreshCw } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import LaserFlow from '../components/react-bits/LaserFlow';
import EventDetailPage, { type EventDetailData } from './EventDetailPage';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import './CinematicEventDetail.css';

export default function CinematicEventDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventDetailData | null>(null);
  const [revision, setRevision] = useState(0);
  const handleEventChange = useCallback((event: EventDetailData | null) => setDetail(event), []);
  const sourceName = detail?.source_id === 'douyin' ? '抖音分享' : detail?.source_id === 'user-upload' ? '文件上传' : detail?.source_id === 'user-concept' ? '概念沉淀' : detail?.source_id || '内容事件';
  const title = detail?.title_cn || detail?.title || '事件详情';
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;
  const eventMeta = useMemo(() => [detail?.topic || '未分类', sourceName, detail?.created_at?.slice(0, 10) || '--'], [detail?.topic, detail?.created_at, sourceName]);

  const status = <section className="ingest-observation cinematic-observation event-detail-status" aria-label="事件详情状态"><div className="panel-status"><i className="signal-dot" /><span>独立事件详情</span></div><span>{title}</span><div className="system-status-summary"><span className="is-good">{detail?.status || 'loading'}</span><span className="is-cyan">{sourceName}</span><span className="is-warn">{detail?.topic || '未分类'}</span></div><div className="panel-detail-grid"><span>事件 ID<b>{id.slice(0, 12) || '--'}</b></span><span>提交时间<b>{detail?.created_at?.slice(0, 10) || '--'}</b></span></div></section>;
  const commands = <section className="ingest-command-launcher event-detail-command-launcher" aria-label="事件详情导航"><div className="launcher-actions"><button className="launcher-action ingest-command-metric is-douyin" onClick={() => navigateWithCurtain('/ingest')}><ArrowLeft size={15} /><b>返回采集</b><span>内容列表</span><small>BACK</small></button><button className="launcher-action ingest-command-metric is-file" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={15} /><b>刷新详情</b><span>重新读取</span><small>REFRESH</small></button><button className="launcher-action ingest-command-metric is-concept" onClick={() => navigateWithCurtain('/events')}><Library size={15} /><b>事件索引</b><span>全局资料</span><small>INDEX</small></button></div></section>;
  const index = <><div className="ingest-topic-orbit event-detail-topic-orbit"><button className="is-active is-gold"><FileText size={14} /><span>当前事件</span></button></div><div className="ingest-index-list event-detail-index"><button className="ingest-index-item is-active" style={{ '--index-depth-scale': 1, '--index-depth-z': '0px', '--index-depth-opacity': 1 } as CSSProperties}><div className="index-title"><b>{title}</b><span><em className="is-cyan">LIVE</em></span></div><small>{eventMeta.join(' · ')}</small></button></div></>;

  return <CinematicTemplatePage className="cinematic-event-detail" profile={profile} topic="violet" style={style} variant="system" status={status} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="事件详情舱" indexAriaLabel="当前事件" index={index} stageAriaLabel="事件详情正文" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} /><EventDetailPage key={revision} embedded eventId={id} onEventChange={handleEventChange} /><div className="laser-media-box event-detail-core-box"><span>EVENT INTELLIGENCE</span><b>{title}</b><div><em>来源<strong>{sourceName}</strong></em><em>分类<strong>{detail?.topic || '--'}</strong></em><em>状态<strong>{detail?.status || '--'}</strong></em></div></div></>} />} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}
