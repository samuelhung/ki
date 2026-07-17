import { useEffect, useState, type CSSProperties } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useCinematicUiScale } from '../components/cinematic/useCinematicUiScale';
import KiNavigationShell from './KiNavigationShell';
import { scheduleCinematicRoutePreload } from './cinematicRoutePreload';
import '../components/cinematic/cinematic.css';
import './CinematicHome.css';

export default function CinematicHome() {
  const uiScale = useCinematicUiScale();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  useEffect(() => scheduleCinematicRoutePreload(
    () => import('./LegacyIngestShellPreview'),
  ), []);

  function submitSearch() {
    const query = search.trim();
    if (!query) return;
    navigate(`/ingest?search=${encodeURIComponent(query)}`);
  }

  return (
    <KiNavigationShell
      className="ki-shell-home cinematic-dashboard"
      sceneVariant="today"
      laserPrimary={false}
      showReveal={false}
      style={{ '--cinematic-ui-scale': uiScale } as CSSProperties}
      topAccessory={
        <label className="ki-ingest-list-search">
          <Search size={14} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && submitSearch()}
            placeholder="搜索内容标题"
          />
        </label>
      }
    >
      <section className="cinematic-hero cinematic-home__hero" aria-label="今日知几">
        <h1>
          <span className="brand-title">知几</span>
          <span className="line3">其神乎 见微知著</span>
        </h1>
        <p>
          知几其神乎。真正的洞察，不在声势浩大处，而在一线微光。见微知著，从细小征兆预见趋势，于万象未形时辨其轮廓。世事常起微末，端倪易被忽略，须心神澄明，方能在众声鼎沸前辨认方向。知几者，知其始亦知其势；观微者，于未显时读懂万象将成。
        </p>
      </section>
    </KiNavigationShell>
  );
}
