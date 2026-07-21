export const MEDIA_CONNECTION_CHANGE_EVENT = 'ki-media-connection-change';
const MEDIA_ROUTE_PREFIX = '/__ki_media/';

interface WorkerLike {
  postMessage(message: unknown): void;
}

interface RegistrationLike {
  active?: WorkerLike | null;
  waiting?: WorkerLike | null;
  installing?: WorkerLike | null;
}

export interface MediaTransportRuntime {
  origin: string;
  register(): Promise<RegistrationLike>;
}

export interface MediaTransportConnection {
  backendUrl: string;
  token: string;
  path?: string;
}

let browserRegistration: Promise<RegistrationLike> | null = null;

function browserRuntime(): MediaTransportRuntime {
  return {
    origin: window.location.origin,
    register() {
      if (!('serviceWorker' in navigator)) {
        return Promise.reject(new Error('Service workers are unavailable'));
      }
      if (!browserRegistration) {
        browserRegistration = navigator.serviceWorker
          .register('/ki-media-sw.js', { scope: '/' })
          .then(async (registration) => registration.active ? registration : navigator.serviceWorker.ready)
          .catch((error) => {
            browserRegistration = null;
            throw error;
          });
      }
      return browserRegistration;
    },
  };
}

function abortError(): DOMException {
  return new DOMException('Media transport setup aborted', 'AbortError');
}

function waitWithAbort<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const abort = () => {
      cleanup();
      reject(abortError());
    };
    const cleanup = () => signal.removeEventListener('abort', abort);
    signal.addEventListener('abort', abort, { once: true });
    promise.then(
      (value) => { cleanup(); signal.aborted ? reject(abortError()) : resolve(value); },
      (error) => { cleanup(); reject(error); },
    );
  });
}

function protectedMediaPath(path: string): boolean {
  return path.startsWith('/ingest/') || path.startsWith('/releases/');
}

export function mediaTransportUrl(path: string): string {
  if (!protectedMediaPath(path)) throw new Error('Unsupported media path');
  return MEDIA_ROUTE_PREFIX + encodeURIComponent(path);
}

export async function synchronizeMediaTransport(
  connection: MediaTransportConnection,
  signal: AbortSignal,
  runtime: MediaTransportRuntime = browserRuntime(),
): Promise<string> {
  const registration = await waitWithAbort(runtime.register(), signal);
  const worker = registration.active || registration.waiting || registration.installing;
  if (!worker) throw new Error('Media service worker is not active');
  const backendOrigin = new URL(connection.backendUrl || runtime.origin, runtime.origin).origin;
  if (signal.aborted) throw abortError();
  worker.postMessage({ type: 'ki-media-config', backendOrigin, token: connection.token });
  return connection.path ? mediaTransportUrl(connection.path) : '';
}

export function notifyMediaTransportConnectionChanged(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(MEDIA_CONNECTION_CHANGE_EVENT));
}
