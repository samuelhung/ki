export interface ApiFetchRuntimeInit extends RequestInit {
  timeoutMs?: number;
}

export interface ApiFetchRuntime {
  getBackendUrl(): string;
  prepareInit(init?: ApiFetchRuntimeInit): ApiFetchRuntimeInit | undefined;
  request(input: RequestInfo | URL, init?: ApiFetchRuntimeInit): Promise<Response>;
}

const PROTECTED_BACKEND_PREFIXES = ['/api/', '/ingest/', '/releases/'];

function isProtectedBackendPath(input: string): boolean {
  return PROTECTED_BACKEND_PREFIXES.some((prefix) => input.startsWith(prefix));
}

export function createApiFetch(runtime: ApiFetchRuntime) {
  return async function apiFetch(
    input: RequestInfo | URL,
    init?: ApiFetchRuntimeInit,
  ): Promise<Response> {
    if (typeof input === 'string' && isProtectedBackendPath(input)) {
      const requestInit = runtime.prepareInit(init);
      return runtime.request(runtime.getBackendUrl() + input, requestInit);
    }
    return runtime.request(input, init);
  };
}
