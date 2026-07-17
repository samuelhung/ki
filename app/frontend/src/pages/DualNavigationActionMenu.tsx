import { memo, type CSSProperties } from 'react';
import type { LucideIcon } from 'lucide-react';

export interface DualNavigationActionItem {
  key: string;
  text: string;
  meta: string;
  accent: string;
  icon: LucideIcon;
  code: string;
  description: string;
  placeholder: string;
  submit: string;
}

interface ActionMenuProps {
  items: DualNavigationActionItem[];
  onSelect: (item: DualNavigationActionItem) => void;
}

interface ActionStyle extends CSSProperties {
  '--action-accent': string;
  '--action-offset': number;
  '--action-distance': number;
}

function DualNavigationActionMenu({ items, onSelect }: ActionMenuProps) {
  return (
    <div className="dual-nav-action-menu is-dock">
      {items.map((item, index) => {
        const offset = index - (items.length - 1) / 2;
        const style: ActionStyle = {
          '--action-accent': item.accent,
          '--action-offset': offset,
          '--action-distance': Math.abs(offset),
        };
        const Icon = item.icon;

        return (
          <button
            key={item.text}
            type="button"
            className="dual-nav-action-item"
            style={style}
            aria-label={item.text}
            title={`${item.text} · ${item.meta}`}
            onPointerUp={() => onSelect(item)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelect(item);
              }
            }}
          >
            <span className="dual-nav-action-item__icon" aria-hidden="true">
              <Icon size={24} strokeWidth={1.55} />
            </span>
            <span className="dual-nav-action-item__copy">
              <strong>{item.text}</strong>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default memo(DualNavigationActionMenu);
