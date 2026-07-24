export const REMOTE_AUTH_REQUIRED_EVENT = 'ki-auth-required';

export interface RemoteUnlockRuntime {
  isDev: boolean;
  protocol: string;
  hostname: string;
  token: string;
}

export function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === 'localhost'
    || normalized === '127.0.0.1'
    || normalized === '::1'
    || normalized === '[::1]';
}

export function shouldRequireRemoteUnlock(runtime: RemoteUnlockRuntime): boolean {
  return !runtime.isDev
    && (runtime.protocol === 'http:' || runtime.protocol === 'https:')
    && !isLoopbackHostname(runtime.hostname)
    && !runtime.token.trim();
}

export function notifyRemoteAuthRequired(target: EventTarget = window): void {
  target.dispatchEvent(new Event(REMOTE_AUTH_REQUIRED_EVENT));
}

export function subscribeRemoteAuthRequired(
  listener: () => void,
  target: EventTarget = window,
): () => void {
  target.addEventListener(REMOTE_AUTH_REQUIRED_EVENT, listener);
  return () => target.removeEventListener(REMOTE_AUTH_REQUIRED_EVENT, listener);
}
