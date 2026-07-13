import { useEffect, useRef, type PointerEvent } from 'react';
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
  { image: 'https://picsum.photos/seed/dn-signals/1000/750', text: 'Signals' },
  { image: 'https://picsum.photos/seed/dn-library/1000/750', text: 'Library' },
  { image: 'https://picsum.photos/seed/dn-topics/1000/750', text: 'Topics' },
  { image: 'https://picsum.photos/seed/dn-chains/1000/750', text: 'Chains' },
  { image: 'https://picsum.photos/seed/dn-workbench/1000/750', text: 'Workbench' },
  { image: 'https://picsum.photos/seed/dn-control/1000/750', text: 'Control' },
  { image: 'https://picsum.photos/seed/dn-observe/1000/750', text: 'Observe' },
  { image: 'https://picsum.photos/seed/dn-archive/1000/750', text: 'Archive' },
  { image: 'https://picsum.photos/seed/dn-synthesis/1000/750', text: 'Synthesis' },
  { image: 'https://picsum.photos/seed/dn-timeline/1000/750', text: 'Timeline' },
];

export default function DualNavigationDemo() {
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
          textColor="#f7f5ff"
        />
      </section>

      <footer className="dual-nav-demo__footer">
        <span>SECONDARY / 10</span>
        <span>STATIC / LOCKED</span>
      </footer>
    </main>
  );
}
