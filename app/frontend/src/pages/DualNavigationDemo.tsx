import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { ArrowUpRight, X } from 'lucide-react';
import CinematicScene from '../components/cinematic/CinematicScene';
import CircularGallery, { type CircularGalleryItem } from '../components/react-bits/CircularGallery';
import GooeyNav, { type GooeyNavItem } from '../components/react-bits/GooeyNav';
import '../components/cinematic/cinematic.css';
import './DualNavigationDemo.css';

const TOP_ITEMS: GooeyNavItem[] = [
  { label: 'HOME', href: '#home' },
  { label: 'INGEST', href: '#ingest' },
  { label: 'SERIES', href: '#series' },
  { label: 'INDUSTRY', href: '#industry' },
  { label: 'TOOLS', href: '#tools' },
  { label: 'SYSTEM', href: '#system' },
];

const BOTTOM_ITEMS: CircularGalleryItem[] = [
  { image: 'https://picsum.photos/seed/action-douyin/1000/750', text: '抖音分享' },
  { image: 'https://picsum.photos/seed/action-upload/1000/750', text: '文件上传' },
  { image: 'https://picsum.photos/seed/action-concept/1000/750', text: '概念沉淀' },
  { image: 'https://picsum.photos/seed/action-scan/1000/750', text: '信息源扫描' },
  { image: 'https://picsum.photos/seed/action-global/1000/750', text: '全局发现' },
  { image: 'https://picsum.photos/seed/action-topic/1000/750', text: '主题发现' },
  { image: 'https://picsum.photos/seed/action-compose/1000/750', text: '自由组题' },
  { image: 'https://picsum.photos/seed/action-question/1000/750', text: '新建问题' },
  { image: 'https://picsum.photos/seed/action-task/1000/750', text: '新建任务' },
  { image: 'https://picsum.photos/seed/action-study/1000/750', text: '新建学习资料' },
];

const ACTION_META: Record<string, { code: string; description: string; placeholder: string; submit: string }> = {
  抖音分享: { code: 'DOUYIN SHARE', description: '粘贴分享文本，接入短视频解析与转写链路。', placeholder: '粘贴抖音分享内容', submit: '提交解析' },
  文件上传: { code: 'FILE UPLINK', description: '投送文档、音频或视频，进入统一内容处理轨道。', placeholder: '选择文件或拖入此处', submit: '选择文件' },
  概念沉淀: { code: 'CONCEPT NODE', description: '记录一个概念、判断或认知片段，交给 AI 结构化整理。', placeholder: '输入需要沉淀的概念', submit: '创建概念' },
  信息源扫描: { code: 'SOURCE SWEEP', description: '启动全源巡航，检查并采集最新外部信号。', placeholder: '可选：限定扫描主题', submit: '启动扫描' },
  全局发现: { code: 'GLOBAL DISCOVERY', description: '扫描全部内容，通过两阶段聚类发现潜在专题。', placeholder: '可选：输入关注领域', submit: '开始发现' },
  主题发现: { code: 'TOPIC DISCOVERY', description: '围绕关键词定向聚合资料并生成专题候选。', placeholder: '输入主题关键词', submit: '扫描主题' },
  自由组题: { code: 'FREE COMPOSE', description: '创建一个自由专题，后续再选择资料和优化命名。', placeholder: '输入专题方向', submit: '创建专题' },
  新建问题: { code: 'NEW QUESTION', description: '建立持续探索的问题，接入资料与多轮脑暴。', placeholder: '输入想持续探索的问题', submit: '创建问题' },
  新建任务: { code: 'NEW TASK', description: '把当前判断收束为可跟踪、可执行的行动事项。', placeholder: '输入任务标题', submit: '创建任务' },
  新建学习资料: { code: 'LEARNING INPUT', description: '录入学习内容或准备上传教材与 OCR 文件。', placeholder: '输入学习资料标题', submit: '创建资料' },
};

export default function DualNavigationDemo() {
  const [activeAction, setActiveAction] = useState<CircularGalleryItem | null>(null);
  const revealFrameRef = useRef(0);
  const revealTargetRef = useRef<HTMLElement | null>(null);
  const revealPointRef = useRef({ x: -9999, y: -9999 });

  useEffect(() => () => {
    if (revealFrameRef.current) cancelAnimationFrame(revealFrameRef.current);
  }, []);

  const handlePointerMove = (event: PointerEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    revealTargetRef.current = event.currentTarget;
    revealPointRef.current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    if (revealFrameRef.current) return;
    revealFrameRef.current = requestAnimationFrame(() => {
      const target = revealTargetRef.current;
      if (target) {
        target.style.setProperty('--reveal-x', `${revealPointRef.current.x}px`);
        target.style.setProperty('--reveal-y', `${revealPointRef.current.y}px`);
      }
      revealFrameRef.current = 0;
    });
  };

  const handlePointerLeave = (event: PointerEvent<HTMLElement>) => {
    revealTargetRef.current = null;
    if (revealFrameRef.current) cancelAnimationFrame(revealFrameRef.current);
    revealFrameRef.current = 0;
    event.currentTarget.style.setProperty('--reveal-x', '-9999px');
    event.currentTarget.style.setProperty('--reveal-y', '-9999px');
  };

  return (
    <main className="dual-nav-demo" onPointerMove={handlePointerMove} onPointerLeave={handlePointerLeave}>
      <CinematicScene focus={0} variant="ingest" laserPrimary />
      <div className="dual-nav-demo__film" aria-hidden="true" />
      <div className="dual-nav-demo__reveal" aria-hidden="true" />

      <header className="dual-nav-demo__top">
        <span className="dual-nav-demo__index">NAV / 01</span>
        <GooeyNav
          items={TOP_ITEMS}
          particleCount={15}
          particleDistances={[90, 10]}
          particleR={100}
          animationTime={600}
          timeVariance={300}
          initialActiveIndex={0}
        />
        <span className="dual-nav-demo__index">PRIMARY</span>
      </header>

      <section className="cinematic-hero dual-nav-demo__hero" aria-label="今日知几">
        <h1>
          <span className="brand-title">知几</span>
          <span className="line3">其神乎 见微知著</span>
        </h1>
        <p>
          知几其神乎。真正的洞察，不在声势浩大处，而在一线微光。见微知著，从细小征兆预见趋势，于万象未形时辨其轮廓。世事常起微末，端倪易被忽略，须心神澄明，方能在众声鼎沸前辨认方向。知几者，知其始亦知其势；观微者，于未显时读懂万象将成。
        </p>
      </section>

      <section className="dual-nav-demo__gallery" aria-label="Independent circular gallery menu">
        <CircularGallery
          items={BOTTOM_ITEMS}
          bend={3}
          borderRadius={0.1}
          scrollSpeed={2.7}
          scrollEase={0.12}
          itemScale={0.34}
          dpr={1.25}
          interactive={false}
          onItemSelect={setActiveAction}
          textColor="#f7f5ff"
        />
      </section>

      <footer className="dual-nav-demo__footer">
        <span>SECONDARY / 10</span>
        <span>STATIC / LOCKED</span>
      </footer>

      {activeAction && (
        <div className="dual-nav-action-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setActiveAction(null)}>
          <section className="dual-nav-action-dialog" role="dialog" aria-modal="true" aria-label={activeAction.text}>
            <button className="dual-nav-action-close" type="button" aria-label="关闭" onClick={() => setActiveAction(null)}><X size={18} /></button>
            <header>
              <span>{ACTION_META[activeAction.text].code}</span>
              <h2>{activeAction.text}</h2>
              <p>{ACTION_META[activeAction.text].description}</p>
            </header>
            <div className="dual-nav-action-field">
              <label htmlFor="dual-nav-action-input">INPUT CHANNEL</label>
              <textarea id="dual-nav-action-input" autoFocus placeholder={ACTION_META[activeAction.text].placeholder} />
            </div>
            <footer>
              <button type="button" onClick={() => setActiveAction(null)}>{ACTION_META[activeAction.text].submit}<ArrowUpRight size={15} /></button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}
