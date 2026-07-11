import React from 'react';
import { useLocation } from 'react-router-dom';
import { cinematicNavHubs } from '../../navigation';
import { computeCinematicNavigationGeometry } from './cinematicNavigationGeometry';

interface Props {
  activeHub: string | null;
  onActiveHubChange: (hub: string | null) => void;
  onNavigate: (path: string) => void;
}

export function getCinematicNavigationGeometry(activeHub: string | null) {
  const activeHubIndex = Math.max(0, cinematicNavHubs.findIndex((hub) => hub.to === activeHub));
  const activeHubChildren = cinematicNavHubs.find((hub) => hub.to === activeHub)?.children || [];
  const { childMenuHeight, childMenuBottom } = computeCinematicNavigationGeometry(
    cinematicNavHubs.length,
    activeHubIndex,
    activeHubChildren.length,
  );

  return { activeHubChildren, childMenuHeight, childMenuBottom };
}

export default function CinematicWorkIndex({ activeHub, onActiveHubChange, onNavigate }: Props) {
  const location = useLocation();
  const currentHub =
    cinematicNavHubs.find((hub) => hub.to === location.pathname || hub.children.some((item) => item.to === location.pathname)) ||
    cinematicNavHubs[0];
  const activeHubKey = activeHub || currentHub.to;
  const { activeHubChildren, childMenuHeight, childMenuBottom } = getCinematicNavigationGeometry(activeHub);

  return (
    <nav
      className="cinematic-work-index"
      aria-label="知几功能索引"
      onMouseLeave={() => onActiveHubChange(null)}
    >
      <div className="cinematic-hub-primary">
        {cinematicNavHubs.map((hub) => {
          const Icon = hub.icon;
          const hasChildren = hub.children.length > 0;
          const active = activeHubKey === hub.to;
          return (
            <button
              key={hub.to}
              className={`${active ? 'is-active' : ''}${hasChildren ? ' has-children' : ''}`}
              aria-expanded={hasChildren ? activeHub === hub.to : undefined}
              onMouseEnter={() => onActiveHubChange(hasChildren ? hub.to : null)}
              onClick={() => {
                if (hasChildren) {
                  onActiveHubChange(hub.to);
                  return;
                }
                onNavigate(hub.to);
              }}
            >
              <Icon size={14} aria-hidden="true" />
              <b>{hub.label}</b>
            </button>
          );
        })}
      </div>

      {activeHubChildren.length > 0 && (
        <div
          className="cinematic-hub-children"
          style={{
            '--hub-child-height': `${childMenuHeight}px`,
            bottom: `${childMenuBottom}px`,
          } as React.CSSProperties}
        >
          {activeHubChildren.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.to} onClick={() => onNavigate(item.to)}>
                <Icon size={13} aria-hidden="true" />
                <b>{item.label}</b>
              </button>
            );
          })}
        </div>
      )}
    </nav>
  );
}
