import {
  ApiRequestError,
  fetchWithPolicy,
  readApiJson,
  type ApiRequestInit,
} from '../../apiRequestPolicy.ts';

export type RemoteUnlockErrorKind =
  | 'empty-token'
  | 'invalid-token'
  | 'network'
  | 'unexpected-status'
  | 'invalid-response'
  | 'unhealthy';

export class RemoteUnlockError extends Error {
  readonly kind: RemoteUnlockErrorKind;

  constructor(kind: RemoteUnlockErrorKind) {
    super(kind);
    this.name = 'RemoteUnlockError';
    this.kind = kind;
  }
}

interface UnlockHealth {
  ok?: boolean;
  database?: { ok?: boolean };
}

type RequestFn = (
  input: RequestInfo | URL,
  init?: ApiRequestInit,
) => Promise<Response>;

export async function validateRemoteUnlockToken(
  token: string,
  options: { endpoint?: string; request?: RequestFn } = {},
): Promise<void> {
  const normalized = token.trim();
  if (!normalized) throw new RemoteUnlockError('empty-token');

  const request = options.request ?? fetchWithPolicy;
  let response: Response;
  try {
    response = await request(options.endpoint ?? '/api/system/health', {
      headers: { Authorization: `Bearer ${normalized}` },
      timeoutMs: 10_000,
    });
  } catch (error) {
    if (error instanceof ApiRequestError
      && (error.kind === 'network' || error.kind === 'timeout')) {
      throw new RemoteUnlockError('network');
    }
    throw new RemoteUnlockError('network');
  }

  if (response.status === 401) throw new RemoteUnlockError('invalid-token');
  if (!response.ok) throw new RemoteUnlockError('unexpected-status');

  let payload: UnlockHealth;
  try {
    payload = await readApiJson<UnlockHealth>(response);
  } catch {
    throw new RemoteUnlockError('invalid-response');
  }
  if (payload.ok !== true || payload.database?.ok !== true) {
    throw new RemoteUnlockError('unhealthy');
  }
}

export function remoteUnlockErrorMessage(error: unknown): string {
  if (!(error instanceof RemoteUnlockError)) return '无法验证访问权限';
  if (error.kind === 'empty-token') return '请输入访问令牌';
  if (error.kind === 'invalid-token') return '访问令牌无效';
  if (error.kind === 'network') return '无法连接知几服务';
  if (error.kind === 'unexpected-status') return '知几服务响应异常';
  return '知几服务验证失败';
}
