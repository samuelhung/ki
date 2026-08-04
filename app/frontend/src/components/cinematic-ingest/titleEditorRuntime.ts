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
        selectedTitle: state.suggestions.includes(action.value) ? action.value : null,
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
        selectedTitle: action.suggestions.includes(state.input) ? state.input : null,
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
  let response: Response;
  try {
    response = await fetcher(`/api/events/${eventId}/title`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_title: value.trim() }),
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
