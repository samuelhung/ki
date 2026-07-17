import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import CinematicScene from './CinematicScene';
import type { CinematicSceneVariant } from './cinematicSceneProfile';

export interface CinematicBackdropRequest {
  variant: CinematicSceneVariant;
  laserPrimary: boolean;
  focus: number;
  className?: string;
}

interface CinematicBackdropContextValue {
  setBackdrop: (request: CinematicBackdropRequest | null) => void;
}

const CinematicBackdropContext = createContext<CinematicBackdropContextValue | null>(null);

export function CinematicBackdropProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<CinematicBackdropRequest | null>(null);
  const setBackdrop = useCallback((next: CinematicBackdropRequest | null) => setRequest(next), []);
  const contextValue = useMemo(() => ({ setBackdrop }), [setBackdrop]);
  const activeRequest = request || { variant: 'today' as const, laserPrimary: false, focus: 0 };

  return (
    <CinematicBackdropContext.Provider value={contextValue}>
      <div
        className={`cinematic-backdrop-host${request?.className ? ` ${request.className}` : ''}${request ? ' is-active' : ''}`}
        aria-hidden="true"
      >
        <CinematicScene
          focus={activeRequest.focus}
          variant={activeRequest.variant}
          laserPrimary={activeRequest.laserPrimary}
          active={Boolean(request)}
        />
      </div>
      {children}
    </CinematicBackdropContext.Provider>
  );
}

export function useCinematicBackdrop() {
  const context = useContext(CinematicBackdropContext);
  if (!context) throw new Error('useCinematicBackdrop must be used within CinematicBackdropProvider');
  return context;
}
