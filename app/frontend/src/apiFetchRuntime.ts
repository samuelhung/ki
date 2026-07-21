export interface ApiFetchRuntimeInit extends RequestInit {
  timeoutMs?: number;
}

export interface ApiFetchRuntime {
  getBackendUrl(): string;
  prepareInit(init?: ApiFetchRuntimeInit): ApiFetchRuntimeInit | undefined;
  request(input: RequestInfo | URL, init?: ApiFetchRuntimeInit): Promise<Response>;
}

export function createApiFetch(runtime: ApiFetchRuntime) {
  return async function apiFetch(
    input: RequestInfo | URL,
    init?: ApiFetchRuntimeInit,
  ): Promise<Response> {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      const requestInit = runtime.prepareInit(init);
      return runtime.request(runtime.getBackendUrl() + input, requestInit);
    }
    return runtime.request(input, init);
  };
}
