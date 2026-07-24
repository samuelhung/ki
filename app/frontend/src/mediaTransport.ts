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

interface MediaTransportMessageEvent {
  data?: {
    type?: string;
    requestId?: string;
  };
  source?: WorkerLike | null;
}

export interface MediaTransportRuntime {
  origin: string;
  register(): Promise<RegistrationLike>;
  addEventListener?(type: 'controllerchange', listener: () => void): void;
  addEventListener?(type: 'message', listener: (event: MediaTransportMessageEvent) => void): void;
  removeEventListener?(type: 'controllerchange', listener: () => void): void;
  removeEventListener?(type: 'message', listener: (event: MediaTransportMessageEvent) => void): void;
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
      const serviceWorker = navigator.serviceWorker;
      if (!serviceWorker) {
        return Promise.reject(new Error('Service workers are unavailable'));
      }
      if (!browserRegistration) {
        browserRegistration = serviceWorker
          .register('/ki-media-sw.js', { scope: '/' })
          .then(async (registration) => registration.active ? registration : serviceWorker.ready)
          .catch((error) => {
            browserRegistration = null;
            throw error;
          });
      }
      return browserRegistration;
    },
    addEventListener(type, listener) {
      navigator.serviceWorker?.addEventListener(type, listener as EventListener);
    },
    removeEventListener(type, listener) {
      navigator.serviceWorker?.removeEventListener(type, listener as EventListener);
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

function normalizedConnection(
  connection: MediaTransportConnection,
  origin: string,
): { backendOrigin: string; token: string } {
  return {
    backendOrigin: new URL(connection.backendUrl || origin, origin).origin,
    token: connection.token,
  };
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
  const config = normalizedConnection(connection, runtime.origin);
  if (signal.aborted) throw abortError();
  worker.postMessage({ type: 'ki-media-config', ...config });
  return connection.path ? mediaTransportUrl(connection.path) : '';
}

export function attachMediaTransportRecovery(
  getConnection: () => MediaTransportConnection,
  runtime: MediaTransportRuntime = browserRuntime(),
): () => void {
  let controller: AbortController | null = null;
  const resend = () => {
    controller?.abort();
    controller = new AbortController();
    void synchronizeMediaTransport(getConnection(), controller.signal, runtime).catch(() => {});
  };
  const respond = (event: MediaTransportMessageEvent) => {
    if (event.data?.type !== 'ki-media-config-request' || !event.data.requestId || !event.source) return;
    event.source.postMessage({
      type: 'ki-media-config',
      requestId: event.data.requestId,
      ...normalizedConnection(getConnection(), runtime.origin),
    });
  };

  runtime.addEventListener?.('controllerchange', resend);
  runtime.addEventListener?.('message', respond);
  return () => {
    runtime.removeEventListener?.('controllerchange', resend);
    runtime.removeEventListener?.('message', respond);
    controller?.abort();
  };
}

export function notifyMediaTransportConnectionChanged(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(MEDIA_CONNECTION_CHANGE_EVENT));
}
