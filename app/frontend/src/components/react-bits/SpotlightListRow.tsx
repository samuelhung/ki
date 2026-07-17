import React, { memo, useRef } from 'react';

interface SpotlightListRowProps extends React.PropsWithChildren {
  active?: boolean;
  className?: string;
  spotlightColor?: string;
}

function SpotlightListRow({
  active = false,
  children,
  className = '',
  spotlightColor = 'rgba(125, 211, 252, 0.2)',
}: SpotlightListRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const row = rowRef.current;
    if (!row) return;
    const bounds = row.getBoundingClientRect();
    row.style.setProperty('--spotlight-x', `${event.clientX - bounds.left}px`);
    row.style.setProperty('--spotlight-y', `${event.clientY - bounds.top}px`);
  }

  return (
    <div
      ref={rowRef}
      className={`ki-spotlight-row${active ? ' is-active' : ''}${className ? ` ${className}` : ''}`}
      style={{ '--spotlight-color': spotlightColor } as React.CSSProperties}
      onPointerMove={handlePointerMove}
    >
      {children}
    </div>
  );
}

export default memo(SpotlightListRow);
