import type { SystemConfig } from './systemTypes';

export async function readSystemConfigResponse(response: Response): Promise<SystemConfig> {
  if (!response.ok) throw new Error('配置请求失败');
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) || !('general' in payload)) {
    throw new Error('配置响应无效');
  }
  const general = (payload as { general?: unknown }).general;
  if (!general || typeof general !== 'object' || Array.isArray(general)) {
    throw new Error('配置响应无效');
  }
  return payload as SystemConfig;
}
