import type { ReactNode } from 'react';
import { MagicBentoCard, MagicBentoGrid } from './KiMagicBento';
import './KiMagicBentoFrame.css';

interface KiMagicBentoFrameProps {
  children: ReactNode;
  className?: string;
  cardClassName?: string;
}

export default function KiMagicBentoFrame({ children, className = '', cardClassName = '' }: KiMagicBentoFrameProps) {
  return (
    <MagicBentoGrid
      className={`ki-magic-bento-frame ${className}`}
      particleCount={18}
      spotlightRadius={420}
      glowColor="132, 0, 255"
      enableTilt
      tiltMax={2.5}
      enableMagnetism
      magnetismStrength={0.02}
      suspendSelector="input, textarea, select, [data-bento-suspend]"
      clickEffect
    >
      <MagicBentoCard className={`ki-magic-bento-frame__card ${cardClassName}`}>
        <span className="ki-magic-bento-frame__electric-edge" aria-hidden="true" />
        {children}
      </MagicBentoCard>
    </MagicBentoGrid>
  );
}
