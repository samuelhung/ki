import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from 'react';
import { apiFetch } from '../../api';
import type { EventItem } from './ingestTypes';
import {
  completeTitleSave,
  createTitleEditorLifecycle,
  createTitleEditorState,
  requestTitleSuggestions,
  saveDisplayTitle,
  titleEditorReducer,
  titleValidationError,
} from './titleEditorRuntime';
import type { SavedEventTitle } from './titleEditorRuntime';

export interface UseTitleEditorOptions {
  activeEventId: string | null;
  onSaved: (eventId: string, titleCn: string) => void;
  onSuccess: () => void;
}

function errorName(reason: unknown): string {
  return reason && typeof reason === 'object' && 'name' in reason
    ? String(reason.name)
    : '';
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export function useTitleEditor({ activeEventId, onSaved, onSuccess }: UseTitleEditorOptions) {
  const [state, dispatch] = useReducer(titleEditorReducer, undefined, createTitleEditorState);
  const lifecycleRef = useRef(createTitleEditorLifecycle());
  const inputRef = useRef('');

  const start = useCallback((event: EventItem) => {
    lifecycleRef.current.abortRequests();
    const initialInput = event.title_cn || event.title || '';
    inputRef.current = initialInput;
    dispatch({ type: 'start', input: initialInput });
  }, []);

  const close = useCallback(() => {
    lifecycleRef.current.abortRequests();
    dispatch({ type: 'close' });
  }, []);

  const changeInput = useCallback((value: string) => {
    inputRef.current = value;
    dispatch({ type: 'change-input', value });
  }, []);

  const selectSuggestion = useCallback((value: string) => {
    inputRef.current = value;
    dispatch({ type: 'select-suggestion', value });
  }, []);

  const generate = useCallback(async () => {
    const token = lifecycleRef.current.beginSuggestion();
    if (!token) return;
    const { eventId } = token;
    dispatch({ type: 'generate-start' });
    try {
      const nextSuggestions = await requestTitleSuggestions(eventId, token.signal, apiFetch);
      if (!lifecycleRef.current.isSuggestionCurrent(token)) return;
      dispatch({ type: 'generate-success', suggestions: nextSuggestions });
    } catch (reason) {
      if (
        lifecycleRef.current.isSuggestionCurrent(token)
        && errorName(reason) !== 'AbortError'
      ) {
        dispatch({ type: 'generate-failure', error: errorMessage(reason, 'AI 标题生成失败') });
      }
    } finally {
      if (lifecycleRef.current.finishSuggestion(token)) {
        dispatch({ type: 'generate-end' });
      }
    }
  }, []);

  const save = useCallback(async () => {
    const value = inputRef.current;
    const validation = titleValidationError(value);
    if (validation) {
      dispatch({ type: 'set-error', error: validation });
      return;
    }
    const token = lifecycleRef.current.beginSave();
    if (!token) return;
    const { eventId } = token;
    dispatch({ type: 'save-start' });
    let result: SavedEventTitle;
    try {
      result = await saveDisplayTitle(eventId, value, token.signal, apiFetch);
    } catch (reason) {
      if (lifecycleRef.current.isSaveCurrent(token) && errorName(reason) !== 'AbortError') {
        dispatch({ type: 'save-failure', error: errorMessage(reason, '保存标题失败') });
      }
      if (lifecycleRef.current.finishSave(token)) {
        dispatch({ type: 'save-end' });
      }
      return;
    }
    if (!lifecycleRef.current.isSaveCurrent(token)) return;
    completeTitleSave(result, { onSaved, onSuccess, onClose: close });
  }, [close, onSaved, onSuccess]);

  useLayoutEffect(() => {
    lifecycleRef.current.commitActiveEvent(activeEventId);
    inputRef.current = '';
    dispatch({ type: 'active-event-changed' });
  }, [activeEventId]);

  useEffect(() => {
    return () => {
      lifecycleRef.current.destroy();
    };
  }, []);

  return {
    ...state,
    validationError: titleValidationError(state.input),
    start,
    close,
    changeInput,
    selectSuggestion,
    generate,
    save,
  };
}
