const MEDIA_ROUTE_PREFIX = '/__ki_media/';
const ALLOWED_PATH_PREFIXES = ['/ingest/', '/releases/'];
const FORWARDED_HEADERS = ['range', 'if-range', 'if-none-match', 'if-modified-since', 'if-unmodified-since'];
const CONFIG_ACK_TIMEOUT_MS = 1500;
const clientConfigs = new Map();
const pendingConfigRequests = new Map();
let configRequestSequence = 0;

function normalizeBackendOrigin(value) {
  if (typeof value !== 'string' || !value) return null;
  try {
    const parsed = new URL(value);
    if (!['http:', 'https:'].includes(parsed.protocol)) return null;
    if (parsed.username || parsed.password || value !== parsed.origin) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function isAllowedPath(pathname) {
  return ALLOWED_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function resolveUpstreamUrl(backendOrigin, protectedPath) {
  const origin = normalizeBackendOrigin(backendOrigin);
  if (!origin || typeof protectedPath !== 'string' || !protectedPath.startsWith('/')) return null;
  try {
    const upstream = new URL(protectedPath, origin);
    if (upstream.origin !== origin || !isAllowedPath(upstream.pathname) || upstream.hash) return null;
    return upstream.href;
  } catch {
    return null;
  }
}

function buildUpstreamHeaders(incoming, token) {
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = incoming.get(name);
    if (value) headers.set(name, value);
  }
  headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

function decodeMediaRoute(requestUrl) {
  const url = new URL(requestUrl);
  if (url.origin !== self.location.origin || url.search || url.hash || !url.pathname.startsWith(MEDIA_ROUTE_PREFIX)) return null;
  const encodedPath = url.pathname.slice(MEDIA_ROUTE_PREFIX.length);
  if (!encodedPath) return null;
  try {
    return decodeURIComponent(encodedPath);
  } catch {
    return null;
  }
}

function acceptClientConfig(clientId, data) {
  const backendOrigin = normalizeBackendOrigin(data.backendOrigin);
  const token = typeof data.token === 'string' ? data.token : '';
  if (!backendOrigin || !token) {
    clientConfigs.delete(clientId);
    return null;
  }
  const config = { backendOrigin, token };
  clientConfigs.set(clientId, config);
  return config;
}

function requestClientConfig(clientId) {
  const existing = pendingConfigRequests.get(clientId);
  if (existing) return existing.promise;

  const requestId = `ki-media-config-${++configRequestSequence}`;
  let finish;
  const promise = new Promise((resolve) => {
    finish = (config) => {
      const pending = pendingConfigRequests.get(clientId);
      if (!pending || pending.requestId !== requestId) return;
      if (pending.timeoutId !== null) clearTimeout(pending.timeoutId);
      pendingConfigRequests.delete(clientId);
      resolve(config);
    };
  });
  const pending = { requestId, promise, finish, timeoutId: null };
  pendingConfigRequests.set(clientId, pending);

  self.clients.get(clientId).then((client) => {
    if (!client || pendingConfigRequests.get(clientId) !== pending) {
      finish(null);
      return;
    }
    pending.timeoutId = setTimeout(() => finish(null), CONFIG_ACK_TIMEOUT_MS);
    client.postMessage({ type: 'ki-media-config-request', requestId });
  }).catch(() => finish(null));

  return promise;
}

async function handleMediaRequest(request, clientId) {
  if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method Not Allowed', { status: 405 });
  const config = clientConfigs.get(clientId) || await requestClientConfig(clientId);
  if (!config?.token) return new Response('Media transport is not configured', { status: 401 });
  const protectedPath = decodeMediaRoute(request.url);
  const upstreamUrl = protectedPath ? resolveUpstreamUrl(config.backendOrigin, protectedPath) : null;
  if (!upstreamUrl) return new Response('Invalid media path', { status: 400 });

  return fetch(upstreamUrl, {
    method: request.method,
    headers: buildUpstreamHeaders(request.headers, config.token),
    cache: 'no-store',
    credentials: 'omit',
    redirect: 'error',
    signal: request.signal,
  });
}

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
  if (event.data?.type !== 'ki-media-config' || !event.source?.id) return;
  const clientId = event.source.id;
  const config = acceptClientConfig(clientId, event.data);
  const pending = pendingConfigRequests.get(clientId);
  if (pending && event.data.requestId === pending.requestId) {
    pending.finish(config);
  }
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin === self.location.origin && url.pathname.startsWith(MEDIA_ROUTE_PREFIX)) {
    event.respondWith(handleMediaRequest(event.request, event.clientId));
  }
});

self.__kiMediaTransportTest = { buildUpstreamHeaders, decodeMediaRoute, handleMediaRequest, resolveUpstreamUrl };
