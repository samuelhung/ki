import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type { EventItem } from './ingestTypes';
import {
  createTitleRequestOwner,
  requestTitleSuggestions,
  saveDisplayTitle,
  titleValidationError,
} from './titleEditorRuntime';

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
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedTitle, setSelectedTitle] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const suggestionOwnerRef = useRef(createTitleRequestOwner());
  const saveOwnerRef = useRef(createTitleRequestOwner());
  const generatingRef = useRef(false);
  const savingRef = useRef(false);
  const inputRef = useRef(input);
  const activeEventIdRef = useRef(activeEventId);
  inputRef.current = input;
  activeEventIdRef.current = activeEventId;

  const start = useCallback((event: EventItem) => {
    suggestionOwnerRef.current.abort();
    saveOwnerRef.current.abort();
    generatingRef.current = false;
    savingRef.current = false;
    const initialInput = event.title_cn || event.title || '';
    inputRef.current = initialInput;
    setInput(initialInput);
    setSuggestions([]);
    setSelectedTitle(null);
    setError('');
    setGenerating(false);
    setSaving(false);
    setOpen(true);
  }, []);

  const close = useCallback(() => {
    suggestionOwnerRef.current.abort();
    saveOwnerRef.current.abort();
    generatingRef.current = false;
    savingRef.current = false;
    setOpen(false);
    setGenerating(false);
    setSaving(false);
    setError('');
  }, []);

  const changeInput = useCallback((value: string) => {
    inputRef.current = value;
    setInput(value);
    setSelectedTitle(suggestions.includes(value) ? value : null);
    setError('');
  }, [suggestions]);

  const selectSuggestion = useCallback((value: string) => {
    inputRef.current = value;
    setInput(value);
    setSelectedTitle(value);
    setError('');
  }, []);

  const generate = useCallback(async () => {
    if (generating || saving) return;
    if (generatingRef.current || savingRef.current) return;
    const eventId = activeEventId;
    if (!eventId) return;
    const token = suggestionOwnerRef.current.start(eventId);
    if (!suggestionOwnerRef.current.isCurrent(token) || activeEventIdRef.current !== eventId) return;
    generatingRef.current = true;
    setGenerating(true);
    setError('');
    try {
      const nextSuggestions = await requestTitleSuggestions(eventId, token.signal, apiFetch);
      if (!suggestionOwnerRef.current.isCurrent(token) || activeEventIdRef.current !== eventId) return;
      setSuggestions(nextSuggestions);
      const currentInput = inputRef.current;
      setSelectedTitle(nextSuggestions.includes(currentInput) ? currentInput : null);
    } catch (reason) {
      if (
        suggestionOwnerRef.current.isCurrent(token)
        && activeEventIdRef.current === eventId
        && errorName(reason) !== 'AbortError'
      ) {
        setError(errorMessage(reason, 'AI 标题生成失败'));
      }
    } finally {
      if (suggestionOwnerRef.current.isCurrent(token) && activeEventIdRef.current === eventId) {
        generatingRef.current = false;
        setGenerating(false);
      }
    }
  }, [activeEventId, generating, saving]);

  const save = useCallback(async () => {
    const validation = titleValidationError(input);
    if (validation) {
      setError(validation);
      return;
    }
    if (saving || generating) return;
    if (savingRef.current || generatingRef.current) return;
    const eventId = activeEventId;
    if (!eventId) return;
    const token = saveOwnerRef.current.start(eventId);
    if (!saveOwnerRef.current.isCurrent(token) || activeEventIdRef.current !== eventId) return;
    savingRef.current = true;
    setSaving(true);
    setError('');
    try {
      const result = await saveDisplayTitle(eventId, input, token.signal, apiFetch);
      if (!saveOwnerRef.current.isCurrent(token) || activeEventIdRef.current !== eventId) return;
      onSaved(result.id, result.title_cn);
      onSuccess();
      close();
    } catch (reason) {
      if (
        saveOwnerRef.current.isCurrent(token)
        && activeEventIdRef.current === eventId
        && errorName(reason) !== 'AbortError'
      ) {
        setError(errorMessage(reason, '保存标题失败'));
      }
    } finally {
      if (saveOwnerRef.current.isCurrent(token) && activeEventIdRef.current === eventId) {
        savingRef.current = false;
        setSaving(false);
      }
    }
  }, [activeEventId, close, generating, input, onSaved, onSuccess, saving]);

  useEffect(() => {
    suggestionOwnerRef.current.abort();
    saveOwnerRef.current.abort();
    generatingRef.current = false;
    savingRef.current = false;
    inputRef.current = '';
    setOpen(false);
    setInput('');
    setSuggestions([]);
    setSelectedTitle(null);
    setGenerating(false);
    setSaving(false);
    setError('');
  }, [activeEventId]);

  useEffect(() => {
    return () => {
      suggestionOwnerRef.current.abort();
      saveOwnerRef.current.abort();
    };
  }, []);

  return {
    open,
    input,
    suggestions,
    selectedTitle,
    generating,
    saving,
    error,
    validationError: titleValidationError(input),
    start,
    close,
    changeInput,
    selectSuggestion,
    generate,
    save,
  };
}
