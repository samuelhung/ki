export interface CinematicRoutePreloadOptions {
  timeout?: number;
  fallbackDelay?: number;
}

interface IdleCallbackDeadline {
  didTimeout: boolean;
  timeRemaining(): number;
}

interface IdleCallbackHost {
  requestIdleCallback?: (
    callback: (deadline: IdleCallbackDeadline) => void,
    options?: { timeout: number },
  ) => number;
  cancelIdleCallback?: (handle: number) => void;
}

export function scheduleCinematicRoutePreload(
  load: () => Promise<unknown>,
  options: CinematicRoutePreloadOptions = {},
) {
  const host = globalThis as typeof globalThis & IdleCallbackHost;
  const timeout = options.timeout ?? 1600;
  const fallbackDelay = options.fallbackDelay ?? 240;
  let cancelled = false;
  let started = false;
  let idleHandle: number | undefined;
  let timerHandle: ReturnType<typeof setTimeout> | undefined;

  const start = () => {
    if (cancelled || started) return;
    started = true;
    void load().catch(() => {});
  };

  if (typeof host.requestIdleCallback === 'function') {
    idleHandle = host.requestIdleCallback(start, { timeout });
  } else {
    timerHandle = setTimeout(start, fallbackDelay);
  }

  return () => {
    cancelled = true;
    if (idleHandle !== undefined) host.cancelIdleCallback?.(idleHandle);
    if (timerHandle !== undefined) clearTimeout(timerHandle);
  };
}
