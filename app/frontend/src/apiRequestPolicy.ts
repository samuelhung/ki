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
    this.name = 'ApiRequestError';
    this.kind = kind;
    this.status = options.status;
    this.cause = options.cause;
  }
}

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function resolveRequestTimeoutMs(init: ApiRequestInit): number {
  if (init.timeoutMs !== undefined) return Math.max(1, init.timeoutMs);
  const method = (init.method || 'GET').toUpperCase();
  return method === 'GET' || method === 'HEAD' ? 30_000 : 210_000;
}

export async function fetchWithPolicy(
  input: RequestInfo | URL,
  init: ApiRequestInit = {},
  fetchImpl: FetchLike = fetch,
): Promise<Response> {
  const callerSignal = init.signal;
  if (callerSignal?.aborted) {
    throw new ApiRequestError('cancelled', '请求已取消', { cause: callerSignal.reason });
  }

  const controller = new AbortController();
  const timeoutMs = resolveRequestTimeoutMs(init);
  let timedOut = false;
  const timeoutId = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort(new DOMException('Request timed out', 'TimeoutError'));
  }, timeoutMs);
  const onCallerAbort = () => controller.abort(callerSignal?.reason);
  callerSignal?.addEventListener('abort', onCallerAbort, { once: true });

  const { timeoutMs: _timeoutMs, ...requestInit } = init;
  try {
    return await fetchImpl(input, { ...requestInit, signal: controller.signal });
  } catch (cause) {
    if (callerSignal?.aborted) {
      throw new ApiRequestError('cancelled', '请求已取消', { cause });
    }
    if (timedOut) {
      throw new ApiRequestError('timeout', `请求超时（${timeoutMs}ms）`, { cause });
    }
    if (cause instanceof ApiRequestError) throw cause;
    throw new ApiRequestError('network', '网络请求失败', { cause });
  } finally {
    globalThis.clearTimeout(timeoutId);
    callerSignal?.removeEventListener('abort', onCallerAbort);
  }
}

export async function readApiJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError('http', `HTTP ${response.status}`, { status: response.status });
  }
  try {
    return await response.json() as T;
  } catch (cause) {
    throw new ApiRequestError('invalid-json', '响应不是有效 JSON', { status: response.status, cause });
  }
}
