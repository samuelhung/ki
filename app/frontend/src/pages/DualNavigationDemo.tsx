import type { PointerEvent } from 'react';
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
];

export default function DualNavigationDemo() {
  const handlePointerMove = (event: PointerEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--reveal-x', `${event.clientX - rect.left}px`);
    event.currentTarget.style.setProperty('--reveal-y', `${event.clientY - rect.top}px`);
  };

  const handlePointerLeave = (event: PointerEvent<HTMLElement>) => {
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

      <section className="dual-nav-demo__center" aria-label="Navigation study title">
        <span>INTERFACE STUDY / 02</span>
        <h1>Dual Navigation</h1>
        <i />
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
          textColor="#f7f5ff"
        />
      </section>

      <footer className="dual-nav-demo__footer">
        <span>SECONDARY / 08</span>
        <span>LOOP 2.7</span>
      </footer>
    </main>
  );
}
