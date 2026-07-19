import type { LucideIcon } from 'lucide-react';
import { X } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import KiMagicBentoFrame from '../components/react-bits/KiMagicBentoFrame';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import './GlobalDockWorkspaceFrame.css';

interface GlobalDockWorkspaceFrameProps {
  action: DualNavigationActionItem;
  children: ReactNode;
  icon: LucideIcon;
  onClose: () => void;
  size?: 'compact' | 'wide';
}

export default function GlobalDockWorkspaceFrame({ action, children, icon: Icon, onClose, size = 'compact' }: GlobalDockWorkspaceFrameProps) {
  const style = { '--action-accent': action.accent } as CSSProperties;
  return (
    <div className="dual-nav-action-backdrop global-dock-backdrop global-dock-workspace-backdrop" style={style} onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`global-dock-workspace-stage is-${size}`}>
        <KiMagicBentoFrame className="global-dock-workspace-frame" cardClassName="global-dock-workspace-card">
          <section className="global-dock-workspace-dialog" role="dialog" aria-modal="true" aria-label={action.text}>
            <button className="global-dock-workspace-close" type="button" aria-label="关闭" onClick={onClose} data-bento-suspend><X /></button>
            <header className="global-dock-workspace-header">
              <span>{action.code}</span>
              <div><Icon /><h2>{action.text}</h2></div>
              <p>{action.description}</p>
            </header>
            <div className="global-dock-workspace-body">{children}</div>
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
}
