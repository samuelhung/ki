import type { ReactNode } from 'react';

interface CinematicLaserWorkspaceProps {
  className?: string;
  ariaLabel: string;
  indexClassName?: string;
  indexAriaLabel: string;
  index: ReactNode;
  stageClassName?: string;
  stageAriaLabel: string;
  stage: ReactNode;
}

export default function CinematicLaserWorkspace({
  className = '',
  ariaLabel,
  indexClassName = '',
  indexAriaLabel,
  index,
  stageClassName = '',
  stageAriaLabel,
  stage,
}: CinematicLaserWorkspaceProps) {
  return (
    <section className={`ingest-laser-console${className ? ` ${className}` : ''}`} aria-label={ariaLabel}>
      <aside className={`ingest-index-strip${indexClassName ? ` ${indexClassName}` : ''}`} aria-label={indexAriaLabel}>
        {index}
      </aside>
      <section className={`ingest-laser-stage${stageClassName ? ` ${stageClassName}` : ''}`} aria-label={stageAriaLabel}>
        {stage}
      </section>
    </section>
  );
}
