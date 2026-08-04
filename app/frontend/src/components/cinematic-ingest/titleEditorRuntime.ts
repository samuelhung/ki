import type { ApiRequestInit } from '../../apiRequestPolicy';

export interface SavedEventTitle {
  id: string;
  title: string;
  title_cn: string;
}

export interface TitleRequestToken {
  eventId: string;
  sequence: number;
  signal: AbortSignal;
}

export type TitleFetcher = (
  input: RequestInfo | URL,
  init?: ApiRequestInit,
) => Promise<Response>;

function isAbortError(reason: unknown): boolean {
  return Boolean(reason && typeof reason === 'object' && 'name' in reason && reason.name === 'AbortError');
}

export function titleValidationError(value: string): string {
  const normalized = value.trim();
  if (!normalized) return '请输入标题';
  if (Array.from(normalized).length > 20) return '标题不能超过 20 个字符';
  return '';
}

export async function requestTitleSuggestions(
  eventId: string,
  signal: AbortSignal,
  fetcher: TitleFetcher,
): Promise<string[]> {
  const response = await fetcher(`/api/events/${eventId}/title/suggestions`, {
    method: 'POST',
    signal,
  });
  if (!response.ok) {
    throw new Error(response.status === 400 ? '当前内容没有可用原文' : 'AI 标题生成失败');
  }

  try {
    const data = await response.json() as { titles?: unknown };
    if (
      !Array.isArray(data.titles)
      || data.titles.length !== 3
      || !data.titles.every((title): title is string => typeof title === 'string')
    ) {
      throw new Error('invalid suggestions');
    }
    return data.titles;
  } catch (reason) {
    if (isAbortError(reason)) throw reason;
    throw new Error('AI 标题生成失败');
  }
}

export async function saveDisplayTitle(
  eventId: string,
  value: string,
  signal: AbortSignal,
  fetcher: TitleFetcher,
): Promise<SavedEventTitle> {
  const response = await fetcher(`/api/events/${eventId}/title`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_title: value.trim() }),
    signal,
  });
  if (!response.ok) throw new Error('保存标题失败');

  try {
    return await response.json() as SavedEventTitle;
  } catch (reason) {
    if (isAbortError(reason)) throw reason;
    throw new Error('保存标题失败');
  }
}

export function createTitleRequestOwner() {
  let current: TitleRequestToken | null = null;
  let currentController: AbortController | null = null;
  let sequence = 0;

  return {
    start(eventId: string): TitleRequestToken {
      currentController?.abort();
      const controller = new AbortController();
      const token = { eventId, sequence: ++sequence, signal: controller.signal };
      currentController = controller;
      current = token;
      return token;
    },
    isCurrent(token: TitleRequestToken): boolean {
      return current === token
        && current.sequence === token.sequence
        && current.eventId === token.eventId
        && !token.signal.aborted;
    },
    abort(): void {
      currentController?.abort();
      currentController = null;
      current = null;
    },
  };
}
