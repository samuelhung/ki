import type { ApiRequestInit } from '../../apiRequestPolicy';

export interface SavedEventTitle {
  id: string;
  title: string;
  title_cn: string;
}

export const DISPLAY_TITLE_EDGE_WHITESPACE = '\u0009\u000a\u000b\u000c\u000d'
  + '\u001c\u001d\u001e\u001f'
  + '\u0020\u0085\u00a0\u1680'
  + '\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a'
  + '\u2028\u2029\u202f\u205f\u3000\ufeff';

const TITLE_EDGE_WHITESPACE = new Set(DISPLAY_TITLE_EDGE_WHITESPACE);

interface EventWithDisplayTitle {
  id: string;
  title_cn?: string;
}

export function normalizeDisplayTitle(value: string): string {
  let start = 0;
  let end = value.length;
  while (start < end && TITLE_EDGE_WHITESPACE.has(value[start])) start += 1;
  while (end > start && TITLE_EDGE_WHITESPACE.has(value[end - 1])) end -= 1;
  return value.slice(start, end);
}

export function createEventTitleOverrides() {
  // One entry per event saved during this mounted session; reads and polling never add entries.
  const titles = new Map<string, string>();

  function apply<T extends EventWithDisplayTitle>(event: T): T {
    const titleCn = titles.get(event.id);
    if (titleCn === undefined || event.title_cn === titleCn) return event;
    return { ...event, title_cn: titleCn };
  }

  return {
    remember(eventId: string, titleCn: string): void {
      titles.set(eventId, titleCn);
    },
    apply,
    applyAll<T extends EventWithDisplayTitle>(events: T[]): T[] {
      return events.map(apply);
    },
    size(): number {
      return titles.size;
    },
  };
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

export interface TitleEditorState {
  open: boolean;
  input: string;
  suggestions: string[];
  selectedTitle: string | null;
  generating: boolean;
  saving: boolean;
  error: string;
}

export type TitleEditorAction =
  | { type: 'active-event-changed' }
  | { type: 'start'; input: string }
  | { type: 'close' }
  | { type: 'change-input'; value: string }
  | { type: 'select-suggestion'; value: string }
  | { type: 'set-error'; error: string }
  | { type: 'generate-start' }
  | { type: 'generate-success'; suggestions: string[] }
  | { type: 'generate-failure'; error: string }
  | { type: 'generate-end' }
  | { type: 'save-start' }
  | { type: 'save-failure'; error: string }
  | { type: 'save-end' };

export function createTitleEditorState(): TitleEditorState {
  return {
    open: false,
    input: '',
    suggestions: [],
    selectedTitle: null,
    generating: false,
    saving: false,
    error: '',
  };
}

export function titleEditorReducer(
  state: TitleEditorState,
  action: TitleEditorAction,
): TitleEditorState {
  switch (action.type) {
    case 'active-event-changed':
      return createTitleEditorState();
    case 'start':
      return { ...createTitleEditorState(), open: true, input: action.input };
    case 'close':
      return { ...state, open: false, generating: false, saving: false, error: '' };
    case 'change-input':
      return {
        ...state,
        input: action.value,
        selectedTitle: null,
        error: '',
      };
    case 'select-suggestion':
      return { ...state, input: action.value, selectedTitle: action.value, error: '' };
    case 'set-error':
      return { ...state, error: action.error };
    case 'generate-start':
      return { ...state, generating: true, error: '' };
    case 'generate-success':
      return {
        ...state,
        suggestions: action.suggestions,
        selectedTitle: null,
      };
    case 'generate-failure':
      return { ...state, error: action.error };
    case 'generate-end':
      return { ...state, generating: false };
    case 'save-start':
      return { ...state, saving: true, error: '' };
    case 'save-failure':
      return { ...state, error: action.error };
    case 'save-end':
      return { ...state, saving: false };
  }
}

function isAbortError(reason: unknown): boolean {
  return Boolean(reason && typeof reason === 'object' && 'name' in reason && reason.name === 'AbortError');
}

function isSavedEventTitle(value: unknown, eventId: string): value is SavedEventTitle {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<Record<keyof SavedEventTitle, unknown>>;
  return candidate.id === eventId
    && typeof candidate.title === 'string'
    && typeof candidate.title_cn === 'string';
}

export function titleValidationError(value: string): string {
  const normalized = normalizeDisplayTitle(value);
  if (!normalized) return '请输入标题';
  if (Array.from(normalized).length > 20) return '标题不能超过 20 个字符';
  return '';
}

export async function requestTitleSuggestions(
  eventId: string,
  signal: AbortSignal,
  fetcher: TitleFetcher,
): Promise<string[]> {
  let response: Response;
  try {
    response = await fetcher(`/api/events/${eventId}/title/suggestions`, {
      method: 'POST',
      signal,
    });
  } catch (reason) {
    if (isAbortError(reason)) throw reason;
    throw new Error('AI 标题生成失败');
  }
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
    const titles = data.titles.map(normalizeDisplayTitle);
    if (titles.some((title) => titleValidationError(title)) || new Set(titles).size !== 3) {
      throw new Error('invalid suggestions');
    }
    return titles;
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
  let response: Response;
  try {
    response = await fetcher(`/api/events/${eventId}/title`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_title: normalizeDisplayTitle(value) }),
      signal,
    });
  } catch (reason) {
    if (isAbortError(reason)) throw reason;
    throw new Error('保存标题失败');
  }
  if (!response.ok) throw new Error('保存标题失败');

  try {
    const data: unknown = await response.json();
    if (!isSavedEventTitle(data, eventId)) throw new Error('invalid saved title');
    return data;
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

export function createTitleEditorLifecycle() {
  const suggestionOwner = createTitleRequestOwner();
  const saveOwner = createTitleRequestOwner();
  let activeEventId: string | null = null;
  let generating = false;
  let saving = false;

  function abortRequests(): void {
    suggestionOwner.abort();
    saveOwner.abort();
    generating = false;
    saving = false;
  }

  function isSuggestionCurrent(token: TitleRequestToken): boolean {
    return token.eventId === activeEventId && suggestionOwner.isCurrent(token);
  }

  function isSaveCurrent(token: TitleRequestToken): boolean {
    return token.eventId === activeEventId && saveOwner.isCurrent(token);
  }

  return {
    commitActiveEvent(eventId: string | null): void {
      activeEventId = eventId;
      abortRequests();
    },
    abortRequests,
    beginSuggestion(): TitleRequestToken | null {
      if (!activeEventId || generating || saving) return null;
      const token = suggestionOwner.start(activeEventId);
      generating = true;
      return token;
    },
    isSuggestionCurrent,
    finishSuggestion(token: TitleRequestToken): boolean {
      if (!isSuggestionCurrent(token)) return false;
      generating = false;
      return true;
    },
    beginSave(): TitleRequestToken | null {
      if (!activeEventId || generating || saving) return null;
      const token = saveOwner.start(activeEventId);
      saving = true;
      return token;
    },
    isSaveCurrent,
    finishSave(token: TitleRequestToken): boolean {
      if (!isSaveCurrent(token)) return false;
      saving = false;
      return true;
    },
    destroy(): void {
      activeEventId = null;
      abortRequests();
    },
  };
}

interface CompleteTitleSaveOptions {
  onSaved: (eventId: string, titleCn: string) => void;
  onSuccess: () => void;
  onClose: () => void;
}

export function completeTitleSave(
  result: SavedEventTitle,
  { onSaved, onSuccess, onClose }: CompleteTitleSaveOptions,
): void {
  let callbackError: unknown;
  try {
    onSaved(result.id, result.title_cn);
  } catch (reason) {
    callbackError = reason;
  }
  try {
    onSuccess();
  } catch (reason) {
    if (callbackError === undefined) callbackError = reason;
  }
  onClose();
  if (callbackError !== undefined) throw callbackError;
}
