import { useEffect } from 'react';
import Ingest from './Ingest';
import KiNavigationShell from './KiNavigationShell';
import { scheduleCinematicRoutePreload } from './cinematicRoutePreload';

export default function LegacyIngestShellPreview() {
  useEffect(() => scheduleCinematicRoutePreload(
    () => import('./CinematicHome'),
  ), []);

  return (
    <KiNavigationShell className="ki-shell-ingest-preview">
      <section className="ki-shell-content" aria-label="旧版内容采集工作区">
        <div className="ki-shell-legacy-ingest">
          <Ingest />
        </div>
      </section>
    </KiNavigationShell>
  );
}
