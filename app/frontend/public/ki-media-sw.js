const MEDIA_ROUTE_PREFIX = '/__ki_media/';
const ALLOWED_PATH_PREFIXES = ['/ingest/', '/releases/'];
const FORWARDED_HEADERS = ['range', 'if-range', 'if-none-match', 'if-modified-since', 'if-unmodified-since'];
const clientConfigs = new Map();

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

async function handleMediaRequest(request, clientId) {
  if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method Not Allowed', { status: 405 });
  const config = clientConfigs.get(clientId);
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
  const backendOrigin = normalizeBackendOrigin(event.data.backendOrigin);
  const token = typeof event.data.token === 'string' ? event.data.token : '';
  if (!backendOrigin || !token) {
    clientConfigs.delete(event.source.id);
    return;
  }
  clientConfigs.set(event.source.id, { backendOrigin, token });
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin === self.location.origin && url.pathname.startsWith(MEDIA_ROUTE_PREFIX)) {
    event.respondWith(handleMediaRequest(event.request, event.clientId));
  }
});

self.__kiMediaTransportTest = { buildUpstreamHeaders, decodeMediaRoute, resolveUpstreamUrl };
