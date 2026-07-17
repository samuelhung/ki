import { useCallback, useEffect, useRef, useState } from 'react';
import Ingest, { type IngestActionRequest } from './Ingest';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import KiNavigationShell from './KiNavigationShell';
import { scheduleCinematicRoutePreload } from './cinematicRoutePreload';

export default function LegacyIngestShellPreview() {
  const [actionRequest, setActionRequest] = useState<IngestActionRequest | null>(null);
  const actionNonceRef = useRef(0);

  useEffect(() => scheduleCinematicRoutePreload(
    () => import('./CinematicHome'),
  ), []);

  const handleGlobalAction = useCallback((item: DualNavigationActionItem) => {
    actionNonceRef.current += 1;
    if (item.key === 'douyin') setActionRequest({ type: 'douyin', nonce: actionNonceRef.current });
    else if (item.key === 'file') setActionRequest({ type: 'file', nonce: actionNonceRef.current });
    else if (item.key === 'concept') setActionRequest({ type: 'concept', nonce: actionNonceRef.current });
    else if (item.key === 'queue') setActionRequest({ type: 'queue', nonce: actionNonceRef.current });
    else return false;
    return true;
  }, []);

  return (
    <KiNavigationShell className="ki-shell-ingest-preview" onGlobalAction={handleGlobalAction}>
      <section className="ki-shell-content" aria-label="旧版内容采集工作区">
        <div className="ki-shell-legacy-ingest">
          <Ingest embedded actionRequest={actionRequest} />
        </div>
      </section>
    </KiNavigationShell>
  );
}
