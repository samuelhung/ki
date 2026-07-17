import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { ArrowUpRight, BrainCircuit, CircleHelp, FileUp, Lightbulb, ListChecks, ListTodo, Radar, ScanSearch, Sparkles, X, Zap } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useCinematicBackdrop } from '../components/cinematic/CinematicBackdropContext';
import type { CinematicSceneVariant } from '../components/cinematic/cinematicSceneProfile';
import GooeyNav, { type GooeyNavItem } from '../components/react-bits/GooeyNav';
import TextType from '../components/react-bits/TextType';
import DualNavigationActionMenu, { type DualNavigationActionItem } from './DualNavigationActionMenu';
import { useCinematicWorkspaceScale } from './useCinematicWorkspaceScale';
import '../components/cinematic/cinematic.css';
import './DualNavigationDemo.css';

const TOP_ITEMS: GooeyNavItem[] = [
  { label: '内容采集', href: '/ingest' },
  { label: '事件列表', href: '/events' },
  { label: '信息源', href: '/sources' },
  { label: '专题系列', href: '/series' },
  { label: '产业链', href: '/industry-chains' },
  { label: '工具箱', href: '/toolbox' },
  { label: '系统中枢', href: '/system' },
];

const GOOEY_PARTICLE_DISTANCES: [number, number] = [90, 10];

const GLOBAL_ACTIONS: DualNavigationActionItem[] = [
  { key: 'douyin', text: '抖音分享', meta: '短视频接入', accent: '#ff5f8f', icon: Zap, code: 'DOUYIN SHARE', description: '粘贴分享文本，接入短视频解析与转写链路。', placeholder: '粘贴抖音分享内容', submit: '提交解析' },
  { key: 'file', text: '文件上传', meta: '本地资料导入', accent: '#ffb35c', icon: FileUp, code: 'FILE UPLINK', description: '投送文档、音频或视频，进入统一内容处理轨道。', placeholder: '选择文件或拖入此处', submit: '选择文件' },
  { key: 'concept', text: '概念沉淀', meta: '认知片段整理', accent: '#d3a2ff', icon: Lightbulb, code: 'CONCEPT NODE', description: '记录一个概念、判断或认知片段，交给 AI 结构化整理。', placeholder: '输入需要沉淀的概念', submit: '创建概念' },
  { key: 'scan', text: '信息源扫描', meta: '外部信号巡航', accent: '#54d8e8', icon: Radar, code: 'SOURCE SWEEP', description: '启动全源巡航，检查并采集最新外部信号。', placeholder: '可选：限定扫描主题', submit: '启动扫描' },
  { key: 'global', text: '全局发现', meta: '跨域聚类发现', accent: '#67a8ff', icon: ScanSearch, code: 'GLOBAL DISCOVERY', description: '扫描全部内容，通过两阶段聚类发现潜在专题。', placeholder: '可选：输入关注领域', submit: '开始发现' },
  { key: 'topic', text: '主题发现', meta: '定向资料聚合', accent: '#ac8cff', icon: Sparkles, code: 'TOPIC DISCOVERY', description: '围绕关键词定向聚合资料并生成专题候选。', placeholder: '输入主题关键词', submit: '扫描主题' },
  { key: 'compose', text: '自由组题', meta: '专题快速创建', accent: '#65d6a1', icon: BrainCircuit, code: 'FREE COMPOSE', description: '创建一个自由专题，后续再选择资料和优化命名。', placeholder: '输入专题方向', submit: '创建专题' },
  { key: 'question', text: '新建问题', meta: '建立持续探索', accent: '#74c7ff', icon: CircleHelp, code: 'NEW QUESTION', description: '建立持续探索的问题，接入资料与多轮脑暴。', placeholder: '输入想持续探索的问题', submit: '创建问题' },
  { key: 'task', text: '新建任务', meta: '行动事项跟踪', accent: '#ffd269', icon: ListTodo, code: 'NEW TASK', description: '把当前判断收束为可跟踪、可执行的行动事项。', placeholder: '输入任务标题', submit: '创建任务' },
  { key: 'queue', text: '处理队列', meta: '摄入任务轨道', accent: '#ff8d72', icon: ListChecks, code: 'INGEST QUEUE', description: '查看正在处理、等待执行以及异常的内容摄入任务。', placeholder: '查看实时处理轨道', submit: '打开队列' },
];

interface KiNavigationShellProps {
  children: ReactNode;
  className?: string;
  onGlobalAction?: (item: DualNavigationActionItem) => boolean;
  sceneVariant?: CinematicSceneVariant;
  laserPrimary?: boolean;
  showReveal?: boolean;
  style?: CSSProperties;
  topAccessory?: ReactNode;
}

function resolveTopIndex(pathname: string) {
  if (pathname === '/demo/ki-ingest' || pathname.startsWith('/ingest')) return 0;
  if (pathname.startsWith('/events')) return 1;
  if (pathname.startsWith('/sources')) return 2;
  if (pathname.startsWith('/series')) return 3;
  if (pathname.startsWith('/industry') || pathname.startsWith('/chains')) return 4;
  if (pathname.startsWith('/toolbox') || pathname.startsWith('/tools')) return 5;
  if (pathname.startsWith('/system') || pathname.startsWith('/settings')) return 6;
  return -1;
}

export default function KiNavigationShell({
  children,
  className = '',
  onGlobalAction,
  sceneVariant = 'ingest',
  laserPrimary = true,
  showReveal = true,
  style,
  topAccessory,
}: KiNavigationShellProps) {
  const [activeAction, setActiveAction] = useState<DualNavigationActionItem | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const activeTopIndex = resolveTopIndex(location.pathname);
  const workspaceScale = useCinematicWorkspaceScale();
  const { setBackdrop } = useCinematicBackdrop();
  const shellStyle = { ...style, '--ki-workspace-scale': workspaceScale } as CSSProperties;
  const mainRef = useRef<HTMLElement>(null);
  const revealFrameRef = useRef(0);
  const revealPointRef = useRef({ x: -9999, y: -9999 });

  useLayoutEffect(() => {
    setBackdrop({
      variant: sceneVariant,
      laserPrimary,
      focus: 0,
      className: sceneVariant === 'today'
        ? 'is-home-active'
        : `is-shell-backdrop-active is-${sceneVariant}-backdrop-active`,
    });
    return () => setBackdrop(null);
  }, [laserPrimary, sceneVariant, setBackdrop]);

  useEffect(() => {
    const target = mainRef.current;
    if (!showReveal || !target || !matchMedia('(pointer: fine)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const handlePointerMove = (event: globalThis.PointerEvent) => {
      revealPointRef.current = { x: event.clientX, y: event.clientY };
      if (revealFrameRef.current) return;
      revealFrameRef.current = requestAnimationFrame(() => {
        target.style.setProperty('--reveal-x', `${revealPointRef.current.x}px`);
        target.style.setProperty('--reveal-y', `${revealPointRef.current.y}px`);
        revealFrameRef.current = 0;
      });
    };
    const handlePointerLeave = () => {
      if (revealFrameRef.current) cancelAnimationFrame(revealFrameRef.current);
      revealFrameRef.current = 0;
      target.style.setProperty('--reveal-x', '-9999px');
      target.style.setProperty('--reveal-y', '-9999px');
    };

    target.addEventListener('pointermove', handlePointerMove, { passive: true });
    target.addEventListener('pointerleave', handlePointerLeave);
    return () => {
      if (revealFrameRef.current) cancelAnimationFrame(revealFrameRef.current);
      target.removeEventListener('pointermove', handlePointerMove);
      target.removeEventListener('pointerleave', handlePointerLeave);
    };
  }, [showReveal]);

  const handleActionSelect = useCallback((item: DualNavigationActionItem) => {
    if (onGlobalAction?.(item)) return;
    setActiveAction(item);
  }, [onGlobalAction]);
  const handleNavigate = useCallback((item: GooeyNavItem) => navigate(item.href), [navigate]);

  return (
    <main ref={mainRef} className={`dual-nav-demo${className ? ` ${className}` : ''}`} style={shellStyle}>
      <div className={sceneVariant === 'today' ? 'cinematic-film' : 'dual-nav-demo__film'} aria-hidden="true" />
      {showReveal && <div className="dual-nav-demo__reveal" aria-hidden="true" />}

      <header className="dual-nav-demo__top">
        <div className="dual-nav-demo__primary">
          <button type="button" className="dual-nav-demo__brand" onClick={() => navigate('/')} aria-label="返回首页">
            <span className="dual-nav-demo__brand-star-track" aria-hidden="true"><i /></span>
            <span className="dual-nav-demo__brand-title">知几</span>
            <TextType
              as="span"
              className="dual-nav-demo__brand-tagline"
              text="其神乎 见微知著"
              typingSpeed={75}
              pauseDuration={1500}
              deletingSpeed={50}
              showCursor={false}
              cursorCharacter="|"
            />
          </button>
          <GooeyNav items={TOP_ITEMS} particleCount={15} particleDistances={GOOEY_PARTICLE_DISTANCES} particleR={100} animationTime={600} timeVariance={300} activeIndex={activeTopIndex} onNavigate={handleNavigate} />
        </div>
        <div id="ki-shell-top-accessory" className="dual-nav-demo__top-accessory">{topAccessory}</div>
      </header>

      {children}

      <section className="dual-nav-demo__gallery" aria-label="Global action dock">
        <DualNavigationActionMenu items={GLOBAL_ACTIONS} onSelect={handleActionSelect} />
      </section>

      <footer className="dual-nav-demo__footer"><span>GLOBAL / 10</span><span>DOCK / LOCKED</span></footer>

      {activeAction && (
        <div className="dual-nav-action-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setActiveAction(null)}>
          <section className="dual-nav-action-dialog" role="dialog" aria-modal="true" aria-label={activeAction.text}>
            <button className="dual-nav-action-close" type="button" aria-label="关闭" onClick={() => setActiveAction(null)}><X size={18} /></button>
            <header><span>{activeAction.code}</span><h2>{activeAction.text}</h2><p>{activeAction.description}</p></header>
            <div className="dual-nav-action-field"><label htmlFor="ki-global-action-input">INPUT CHANNEL</label><textarea id="ki-global-action-input" autoFocus placeholder={activeAction.placeholder} /></div>
            <footer><button type="button" onClick={() => setActiveAction(null)}>{activeAction.submit}<ArrowUpRight size={15} /></button></footer>
          </section>
        </div>
      )}
    </main>
  );
}
