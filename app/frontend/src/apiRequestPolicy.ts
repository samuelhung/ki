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
  const requestSignal = embeddedRequest(input)?.signal;
  const callerSignals = [requestSignal, init.signal]
    .filter((signal): signal is AbortSignal => Boolean(signal))
    .filter((signal, index, signals) => signals.indexOf(signal) === index);
  const abortedSignal = callerSignals.find((signal) => signal.aborted);
  if (abortedSignal) {
    throw new ApiRequestError('cancelled', '请求已取消', { cause: abortedSignal.reason });
  }

  const timeoutMs = resolveRequestTimeoutMs(init, input);
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const combinedSignal = AbortSignal.any([...callerSignals, timeoutSignal]);

  const { timeoutMs: _timeoutMs, ...requestInit } = init;
  try {
    return await fetchImpl(input, { ...requestInit, signal: combinedSignal });
  } catch (cause) {
    if (callerSignals.some((signal) => signal.aborted)) {
      throw new ApiRequestError('cancelled', '请求已取消', { cause });
    }
    if (timeoutSignal.aborted) {
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
