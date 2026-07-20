export type ApiRequestErrorKind = 'timeout' | 'cancelled' | 'network' | 'http' | 'invalid-json';

export interface ApiRequestInit extends RequestInit {
  timeoutMs?: number;
}

export class ApiRequestError extends Error {
  readonly kind: ApiRequestErrorKind;
  readonly status?: number;
  readonly cause?: unknown;

  constructor(kind: ApiRequestErrorKind, message: string, options: { status?: number; cause?: unknown } = {}) {
    super(message);
    this.name = kind === 'cancelled' ? 'AbortError' : 'ApiRequestError';
    this.kind = kind;
    this.status = options.status;
    this.cause = options.cause;
  }
}

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function embeddedRequest(input?: RequestInfo | URL): Request | undefined {
  return typeof Request !== 'undefined' && input instanceof Request ? input : undefined;
}

interface RequestSignalComposition {
  signal: AbortSignal;
  didTimeout(): boolean;
  cleanup(): void;
}

function composeRequestSignal(callerSignal: AbortSignal | undefined, timeoutMs: number): RequestSignalComposition {
  if (typeof AbortSignal.timeout === 'function' && typeof AbortSignal.any === 'function') {
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    return {
      signal: callerSignal ? AbortSignal.any([callerSignal, timeoutSignal]) : timeoutSignal,
      didTimeout: () => timeoutSignal.aborted,
      cleanup: () => undefined,
    };
  }

  const controller = new AbortController();
  let timedOut = false;
  let timeoutId: ReturnType<typeof globalThis.setTimeout> | undefined;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);
  const cleanup = () => {
    if (timeoutId !== undefined) globalThis.clearTimeout(timeoutId);
    callerSignal?.removeEventListener('abort', abortFromCaller);
  };

  try {
    timeoutId = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort(new DOMException('Request timed out', 'TimeoutError'));
    }, timeoutMs);
    callerSignal?.addEventListener('abort', abortFromCaller, { once: true });
    controller.signal.addEventListener('abort', cleanup, { once: true });
  } catch (cause) {
    cleanup();
    throw cause;
  }

  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    cleanup,
  };
}

export function resolveRequestTimeoutMs(init: ApiRequestInit, input?: RequestInfo | URL): number {
  if (init.timeoutMs !== undefined) return Math.max(1, init.timeoutMs);
  const method = (init.method || embeddedRequest(input)?.method || 'GET').toUpperCase();
  return method === 'GET' || method === 'HEAD' ? 30_000 : 210_000;
}

export async function fetchWithPolicy(
  input: RequestInfo | URL,
  init: ApiRequestInit = {},
  fetchImpl: FetchLike = fetch,
): Promise<Response> {
  const callerSignal = init.signal !== undefined
    ? init.signal || undefined
    : embeddedRequest(input)?.signal;
  if (callerSignal?.aborted) {
    throw new ApiRequestError('cancelled', '请求已取消', { cause: callerSignal.reason });
  }

  const timeoutMs = resolveRequestTimeoutMs(init, input);
  let composition: RequestSignalComposition;
  try {
    composition = composeRequestSignal(callerSignal, timeoutMs);
  } catch (cause) {
    throw new ApiRequestError('network', '请求初始化失败', { cause });
  }

  const { timeoutMs: _timeoutMs, ...requestInit } = init;
  try {
    return await fetchImpl(input, { ...requestInit, signal: composition.signal });
  } catch (cause) {
    composition.cleanup();
    if (callerSignal?.aborted) {
      throw new ApiRequestError('cancelled', '请求已取消', { cause });
    }
    if (composition.didTimeout()) {
      throw new ApiRequestError('timeout', `请求超时（${timeoutMs}ms）`, { cause });
    }
    if (cause instanceof ApiRequestError) throw cause;
    throw new ApiRequestError('network', '网络请求失败', { cause });
  }
}

export async function readApiJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError('http', `HTTP ${response.status}`, { status: response.status });
  }
  try {
    return await response.json() as T;
  } catch (cause) {
    if (cause instanceof ApiRequestError) throw cause;
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw new ApiRequestError('cancelled', '请求已取消', { status: response.status, cause });
    }
    if (cause instanceof DOMException && cause.name === 'TimeoutError') {
      throw new ApiRequestError('timeout', '响应读取超时', { status: response.status, cause });
    }
    throw new ApiRequestError('invalid-json', '响应不是有效 JSON', { status: response.status, cause });
  }
}
