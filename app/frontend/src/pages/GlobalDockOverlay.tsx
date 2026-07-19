import { lazy, Suspense } from 'react';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';

const GlobalDockAccessOverlay = lazy(() => import('./GlobalDockAccessOverlay'));
const GlobalDockConceptOverlay = lazy(() => import('./GlobalDockConceptOverlay'));
const GlobalDockSourcesOverlay = lazy(() => import('./GlobalDockSourcesOverlay'));
const GlobalDockEventsOverlay = lazy(() => import('./GlobalDockEventsOverlay'));
const GlobalDockDiscoveryOverlay = lazy(() => import('./GlobalDockDiscoveryOverlay'));
const GlobalDockQuestionOverlay = lazy(() => import('./GlobalDockQuestionOverlay'));
const GlobalDockTaskOverlay = lazy(() => import('./GlobalDockTaskOverlay'));
const GlobalDockQueueOverlay = lazy(() => import('./GlobalDockQueueOverlay'));
const GlobalDockOverviewOverlay = lazy(() => import('./GlobalDockOverviewOverlay'));

const fallback = <div className="dual-nav-action-backdrop global-dock-backdrop" />;

export default function GlobalDockOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  if (action.key === 'overview') return <Suspense fallback={fallback}><GlobalDockOverviewOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'access') return <Suspense fallback={fallback}><GlobalDockAccessOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'concept') return <Suspense fallback={fallback}><GlobalDockConceptOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'sources') return <Suspense fallback={fallback}><GlobalDockSourcesOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'events') return <Suspense fallback={fallback}><GlobalDockEventsOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'discovery') return <Suspense fallback={fallback}><GlobalDockDiscoveryOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'question') return <Suspense fallback={fallback}><GlobalDockQuestionOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'task') return <Suspense fallback={fallback}><GlobalDockTaskOverlay action={action} onClose={onClose} /></Suspense>;
  if (action.key === 'queue') return <Suspense fallback={fallback}><GlobalDockQueueOverlay action={action} onClose={onClose} /></Suspense>;
  return null;
}
