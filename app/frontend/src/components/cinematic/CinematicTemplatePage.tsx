import type { CSSProperties, ReactNode } from 'react';
import CinematicScene from './CinematicScene';
import CinematicWorkIndex from './CinematicWorkIndex';
import type { CinematicSceneVariant } from './cinematicSceneProfile';

interface CinematicTemplatePageProps {
  className?: string;
  profile: string;
  topic: string;
  style: CSSProperties;
  variant: CinematicSceneVariant;
  status: ReactNode;
  commands: ReactNode;
  workspace: ReactNode;
  shellExtras?: ReactNode;
  environmentOverlay?: ReactNode;
  overlays?: ReactNode;
  trailing?: ReactNode;
  activeHub: string | null;
  onActiveHubChange: (hub: string | null) => void;
  onNavigate: (path: string) => void;
}

export default function CinematicTemplatePage({
  className = '',
  profile,
  topic,
  style,
  variant,
  status,
  commands,
  workspace,
  shellExtras,
  environmentOverlay,
  overlays,
  trailing,
  activeHub,
  onActiveHubChange,
  onNavigate,
}: CinematicTemplatePageProps) {
  return (
    <div
      className={`cinematic-ingest cinematic-dashboard${className ? ` ${className}` : ''}`}
      data-template-profile={profile}
      data-topic={topic}
      style={style}
    >
      <CinematicScene focus={0} variant={variant} laserPrimary />
      <div className="ingest-galaxy-layer" aria-hidden="true" />
      <div className="ingest-threads-layer" aria-hidden="true" />
      {environmentOverlay}
      <div className="cinematic-film" />
      <div className="ingest-signal-grid" aria-hidden="true" />
      <div className="ingest-orbit-core" aria-hidden="true"><i /><i /><i /></div>

      <main className="cinematic-ingest-shell">
        {status}
        {commands}
        {workspace}
        {shellExtras}
      </main>

      {overlays}
      <CinematicWorkIndex
        activeHub={activeHub}
        onActiveHubChange={onActiveHubChange}
        onNavigate={onNavigate}
      />
      {trailing}
    </div>
  );
}
