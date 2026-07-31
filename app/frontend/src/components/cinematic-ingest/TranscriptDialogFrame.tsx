import type { LucideIcon } from 'lucide-react';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import KiMagicBentoFrame from '../react-bits/KiMagicBentoFrame';
import '../../pages/GlobalDockWorkspaceFrame.css';

interface TranscriptDialogFrameProps {
  open: boolean;
  eyebrow: string;
  title: string;
  titleId: string;
  description: string;
  icon: LucideIcon;
  dialogClassName: string;
  closeDisabled?: boolean;
  navigation?: ReactNode;
  children: ReactNode;
  onClose: () => void;
}

export function TranscriptDialogFrame({
  open,
  eyebrow,
  title,
  titleId,
  description,
  icon: Icon,
  dialogClassName,
  closeDisabled = false,
  navigation,
  children,
  onClose,
}: TranscriptDialogFrameProps) {
  if (!open) return null;
  const portalHost = document.querySelector<HTMLElement>('.dual-nav-demo') || document.body;
  const dialog = (
    <div
      className="dual-nav-action-backdrop global-dock-backdrop global-dock-workspace-backdrop transcript-dialog-backdrop transcript-workspace-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !closeDisabled) onClose();
      }}
    >
      <div className="global-dock-workspace-stage is-wide transcript-dialog-stage">
        <KiMagicBentoFrame className="global-dock-workspace-frame" cardClassName="global-dock-workspace-card">
          <section className={`global-dock-workspace-dialog ${dialogClassName}`} role="dialog" aria-modal="true" aria-labelledby={titleId}>
            <button type="button" className="global-dock-workspace-close" onClick={onClose} disabled={closeDisabled} aria-label="关闭" data-bento-suspend>
              <X />
            </button>
            <header className="global-dock-workspace-header">
              <span>{eyebrow}</span>
              <div><Icon /><h2 id={titleId}>{title}</h2></div>
              <p>{description}</p>
            </header>
            {navigation}
            <div className="global-dock-workspace-body transcript-dialog-workspace-body">
              {children}
            </div>
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
  return createPortal(dialog, portalHost);
}
