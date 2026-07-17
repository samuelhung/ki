import { useState } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import CinematicScene from '../components/cinematic/CinematicScene';
import GooeyNav, { type GooeyNavItem } from '../components/react-bits/GooeyNav';
import TextType from '../components/react-bits/TextType';
import '../components/cinematic/cinematic.css';
import './BrandDepthDemo.css';

const DEMO_HREF = '/demo/brand-depth';

const NAV_ITEMS: GooeyNavItem[] = [
  { label: '内容采集', href: DEMO_HREF },
  { label: '事件列表', href: DEMO_HREF },
  { label: '信息源', href: DEMO_HREF },
  { label: '专题系列', href: DEMO_HREF },
  { label: '产业链', href: DEMO_HREF },
  { label: '工具箱', href: DEMO_HREF },
  { label: '系统中枢', href: DEMO_HREF },
];

function DepthBrand() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className="brand-depth-demo__brand brand-depth-demo__brand--aperture"
      onClick={() => navigate('/')}
      aria-label="返回首页"
    >
      <span className="brand-depth-demo__aperture-track" aria-hidden="true"><i /></span>
      <span className="brand-depth-demo__title">知几</span>
      <TextType
        as="span"
        className="brand-depth-demo__motto"
        text="其神乎 见微知著"
        typingSpeed={75}
        pauseDuration={1500}
        deletingSpeed={50}
        showCursor={false}
        cursorCharacter="|"
      />
    </button>
  );
}

function DepthDemoRow() {
  const [activeIndex, setActiveIndex] = useState(0);
  return (
    <section className="brand-depth-demo__row" aria-label="空间光缝">
      <span className="brand-depth-demo__index">01 / 空间光缝</span>
      <div className="brand-depth-demo__bar">
        <DepthBrand />
        <div className="brand-depth-demo__nav">
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
        <label className="brand-depth-demo__search">
          <Search size={14} />
          <input type="search" placeholder="搜索内容标题" aria-label="搜索内容标题" />
          <small>61</small>
        </label>
      </div>
    </section>
  );
}

export default function BrandDepthDemo() {
  return (
    <main className="brand-depth-demo">
      <CinematicScene focus={0} variant="ingest" laserPrimary />
      <div className="brand-depth-demo__film" aria-hidden="true" />
      <header className="brand-depth-demo__heading">
        <span>KI / SPATIAL BRAND STUDY</span>
        <span>DEPTH LOCKUP / 01</span>
      </header>
      <div className="brand-depth-demo__stack">
        <DepthDemoRow />
      </div>
    </main>
  );
}
