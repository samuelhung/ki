import { useState } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import CinematicScene from '../components/cinematic/CinematicScene';
import GooeyNav, { type GooeyNavItem } from '../components/react-bits/GooeyNav';
import '../components/cinematic/cinematic.css';
import './BrandLockupDemo.css';

const DEMO_HREF = '/demo/brand-lockups';

const NAV_ITEMS: GooeyNavItem[] = [
  { label: '内容采集', href: DEMO_HREF },
  { label: '事件列表', href: DEMO_HREF },
  { label: '信息源', href: DEMO_HREF },
  { label: '专题系列', href: DEMO_HREF },
  { label: '产业链', href: DEMO_HREF },
  { label: '工具箱', href: DEMO_HREF },
  { label: '系统中枢', href: DEMO_HREF },
];

type BrandVariant = 'signature' | 'offset' | 'quiet';

const VARIANT_LABELS: Record<BrandVariant, string> = {
  signature: '单行印记',
  offset: '错位题签',
  quiet: '留白铭牌',
};

function BrandMark({ variant }: { variant: BrandVariant }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className={`brand-lockup-demo__brand brand-lockup-demo__brand--${variant}`}
      onClick={() => navigate('/')}
      aria-label="返回首页"
    >
      <span className="brand-lockup-demo__title">知几</span>
      {variant !== 'quiet' && <span className="brand-lockup-demo__motto">其神乎 见微知著</span>}
    </button>
  );
}

function BrandDemoRow({ variant, index }: { variant: BrandVariant; index: number }) {
  const [activeIndex, setActiveIndex] = useState(0);

  return (
    <section className="brand-lockup-demo__row" aria-label={VARIANT_LABELS[variant]}>
      <span className="brand-lockup-demo__index">0{index} / {VARIANT_LABELS[variant]}</span>
      <div className="brand-lockup-demo__bar">
        <BrandMark variant={variant} />
        <div className={`brand-lockup-demo__nav brand-lockup-demo__nav--${variant}`}>
          {variant === 'quiet' && <span className="brand-lockup-demo__quiet-motto">其神乎 见微知著</span>}
          <GooeyNav
            items={NAV_ITEMS}
            activeIndex={activeIndex}
            onNavigate={(_, nextIndex) => setActiveIndex(nextIndex)}
            particleCount={12}
            particleDistances={[72, 8]}
            particleR={82}
            animationTime={520}
            timeVariance={220}
          />
        </div>
        <label className="brand-lockup-demo__search">
          <Search size={14} />
          <input type="search" placeholder="搜索内容标题" aria-label="搜索内容标题" />
          <small>61</small>
        </label>
      </div>
    </section>
  );
}

export default function BrandLockupDemo() {
  return (
    <main className="brand-lockup-demo">
      <CinematicScene focus={0} variant="ingest" laserPrimary />
      <div className="brand-lockup-demo__film" aria-hidden="true" />
      <header className="brand-lockup-demo__heading">
        <span>KI / BRAND LOCKUP STUDY</span>
        <span>TOP NAVIGATION / 03</span>
      </header>
      <div className="brand-lockup-demo__stack">
        <BrandDemoRow variant="signature" index={1} />
        <BrandDemoRow variant="offset" index={2} />
        <BrandDemoRow variant="quiet" index={3} />
      </div>
    </main>
  );
}
