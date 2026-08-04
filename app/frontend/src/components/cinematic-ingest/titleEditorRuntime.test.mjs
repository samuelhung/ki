import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import * as titleRuntime from './titleEditorRuntime.ts';
import {
  createTitleRequestOwner,
  requestTitleSuggestions,
  saveDisplayTitle,
  titleValidationError,
} from './titleEditorRuntime.ts';

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

test('title validation trims input and rejects empty titles', () => {
  assert.equal(titleValidationError('  \n  '), '请输入标题');
  assert.equal(titleValidationError('  正常标题  '), '');
});

test('title validation counts Chinese characters by Unicode code point', () => {
  assert.equal(titleValidationError('汉'.repeat(20)), '');
  assert.equal(titleValidationError('汉'.repeat(21)), '标题不能超过 20 个字符');
});

test('title validation counts non-BMP characters by Unicode code point', () => {
  assert.equal(titleValidationError('😀'.repeat(20)), '');
  assert.equal(titleValidationError('😀'.repeat(21)), '标题不能超过 20 个字符');
});

test('title suggestions use the event endpoint, POST, caller signal, and exactly three strings', async () => {
  const controller = new AbortController();
  let captured;
  const fetcher = async (input, init) => {
    captured = { input, init };
    return jsonResponse({ titles: ['标题一', '标题二', '标题三'] });
  };

  const suggestions = await requestTitleSuggestions('event-1', controller.signal, fetcher);

  assert.deepEqual(suggestions, ['标题一', '标题二', '标题三']);
  assert.equal(captured.input, '/api/events/event-1/title/suggestions');
  assert.equal(captured.init.method, 'POST');
  assert.equal(captured.init.signal, controller.signal);
});

test('title suggestions expose stable errors for 400 and generic HTTP failures', async () => {
  await assert.rejects(
    requestTitleSuggestions('event-1', new AbortController().signal, async () => new Response('', { status: 400 })),
    { message: '当前内容没有可用原文' },
  );
  await assert.rejects(
    requestTitleSuggestions('event-1', new AbortController().signal, async () => new Response('', { status: 502 })),
    { message: 'AI 标题生成失败' },
  );
});

test('title suggestions normalize request-stage failures', async () => {
  await assert.rejects(
    requestTitleSuggestions('event-1', new AbortController().signal, async () => {
      throw new Error('network detail');
    }),
    { message: 'AI 标题生成失败' },
  );
});

test('title suggestions preserve request-stage cancellation', async () => {
  const aborted = new DOMException('Aborted', 'AbortError');
  await assert.rejects(
    requestTitleSuggestions('event-1', new AbortController().signal, async () => {
      throw aborted;
    }),
    (reason) => reason === aborted,
  );
});

test('title suggestions reject bad JSON and payloads that are not exactly three strings', async () => {
  await assert.rejects(
    requestTitleSuggestions('event-1', new AbortController().signal, async () => new Response('{bad json')),
    { message: 'AI 标题生成失败' },
  );
  for (const payload of [
    { titles: ['一', '二'] },
    { titles: ['一', '二', '三', '四'] },
    { titles: ['一', 2, '三'] },
  ]) {
    await assert.rejects(
      requestTitleSuggestions('event-1', new AbortController().signal, async () => jsonResponse(payload)),
      { message: 'AI 标题生成失败' },
    );
  }
});

test('title suggestions preserve cancellation while parsing a response body', async () => {
  const aborted = new DOMException('Aborted', 'AbortError');
  await assert.rejects(
    requestTitleSuggestions('event-1', new AbortController().signal, async () => ({
      ok: true,
      json: async () => { throw aborted; },
    })),
    (reason) => reason === aborted,
  );
});

test('title save sends a trimmed JSON display title and returns authoritative event fields', async () => {
  const controller = new AbortController();
  let captured;
  const authoritative = { id: 'event-1', title: 'Original', title_cn: '服务端标题' };
  const fetcher = async (input, init) => {
    captured = { input, init };
    return jsonResponse(authoritative);
  };

  const saved = await saveDisplayTitle('event-1', '  客户端标题  ', controller.signal, fetcher);

  assert.deepEqual(saved, authoritative);
  assert.equal(captured.input, '/api/events/event-1/title');
  assert.equal(captured.init.method, 'PUT');
  assert.deepEqual(captured.init.headers, { 'Content-Type': 'application/json' });
  assert.equal(captured.init.signal, controller.signal);
  assert.equal(captured.init.body, JSON.stringify({ display_title: '客户端标题' }));
});

test('title save exposes a stable error for HTTP failures and bad JSON', async () => {
  await assert.rejects(
    saveDisplayTitle('event-1', '标题', new AbortController().signal, async () => new Response('', { status: 502 })),
    { message: '保存标题失败' },
  );
  await assert.rejects(
    saveDisplayTitle('event-1', '标题', new AbortController().signal, async () => new Response('{bad json')),
    { message: '保存标题失败' },
  );
});

test('title save rejects malformed or mismatched authoritative event fields', async () => {
  for (const payload of [
    null,
    {},
    { id: 'event-1', title: 42, title_cn: '标题' },
    { id: 'event-1', title: 'Original', title_cn: 42 },
    { id: 'event-2', title: 'Original', title_cn: '标题' },
  ]) {
    await assert.rejects(
      saveDisplayTitle(
        'event-1',
        '标题',
        new AbortController().signal,
        async () => jsonResponse(payload),
      ),
      { message: '保存标题失败' },
    );
  }
});

test('title save normalizes request-stage failures', async () => {
  await assert.rejects(
    saveDisplayTitle('event-1', '标题', new AbortController().signal, async () => {
      throw new Error('network detail');
    }),
    { message: '保存标题失败' },
  );
});

test('title save preserves request-stage cancellation', async () => {
  const aborted = new DOMException('Aborted', 'AbortError');
  await assert.rejects(
    saveDisplayTitle('event-1', '标题', new AbortController().signal, async () => {
      throw aborted;
    }),
    (reason) => reason === aborted,
  );
});

test('title save preserves cancellation while parsing a response body', async () => {
  const aborted = new DOMException('Aborted', 'AbortError');
  await assert.rejects(
    saveDisplayTitle('event-1', '标题', new AbortController().signal, async () => ({
      ok: true,
      json: async () => { throw aborted; },
    })),
    (reason) => reason === aborted,
  );
});

test('request ownership suppresses stale A-B-A responses and aborts actual signals', () => {
  const owners = createTitleRequestOwner();
  const staleA = owners.start('event-a');
  const eventB = owners.start('event-b');
  const currentA = owners.start('event-a');

  assert.equal(staleA.signal.aborted, true);
  assert.equal(eventB.signal.aborted, true);
  assert.equal(owners.isCurrent(staleA), false);
  assert.equal(owners.isCurrent(eventB), false);
  assert.equal(owners.isCurrent(currentA), true);
  assert.ok(staleA.sequence < eventB.sequence && eventB.sequence < currentA.sequence);

  owners.abort();
  assert.equal(currentA.signal.aborted, true);
  assert.equal(owners.isCurrent(currentA), false);
});

test('title editor lifecycle changes owners only when an active event commits', () => {
  const lifecycle = titleRuntime.createTitleEditorLifecycle();
  lifecycle.commitActiveEvent('event-a');
  const staleA = lifecycle.beginSuggestion();
  assert.ok(staleA);

  // A speculative B render does not call commitActiveEvent.
  assert.equal(lifecycle.isSuggestionCurrent(staleA), true);
  lifecycle.commitActiveEvent('event-b');
  assert.equal(staleA.signal.aborted, true);
  assert.equal(lifecycle.isSuggestionCurrent(staleA), false);

  const eventB = lifecycle.beginSuggestion();
  assert.ok(eventB);
  lifecycle.commitActiveEvent('event-a');
  const currentA = lifecycle.beginSuggestion();
  assert.ok(currentA);
  assert.equal(eventB.signal.aborted, true);
  assert.equal(lifecycle.isSuggestionCurrent(eventB), false);
  assert.equal(lifecycle.isSuggestionCurrent(currentA), true);
  assert.ok(staleA.sequence < eventB.sequence && eventB.sequence < currentA.sequence);
});

test('title editor lifecycle aborts close and unmount work', () => {
  const closeLifecycle = titleRuntime.createTitleEditorLifecycle();
  closeLifecycle.commitActiveEvent('event-a');
  const suggestion = closeLifecycle.beginSuggestion();
  assert.ok(suggestion);
  closeLifecycle.abortRequests();
  assert.equal(suggestion.signal.aborted, true);
  assert.equal(closeLifecycle.isSuggestionCurrent(suggestion), false);

  const unmountLifecycle = titleRuntime.createTitleEditorLifecycle();
  unmountLifecycle.commitActiveEvent('event-a');
  const save = unmountLifecycle.beginSave();
  assert.ok(save);
  unmountLifecycle.destroy();
  assert.equal(save.signal.aborted, true);
  assert.equal(unmountLifecycle.isSaveCurrent(save), false);
});

test('title editor lifecycle blocks double submits and generation-save overlap', () => {
  const lifecycle = titleRuntime.createTitleEditorLifecycle();
  lifecycle.commitActiveEvent('event-a');
  const suggestion = lifecycle.beginSuggestion();
  assert.ok(suggestion);
  assert.equal(lifecycle.beginSuggestion(), null);
  assert.equal(lifecycle.beginSave(), null);
  assert.equal(lifecycle.finishSuggestion(suggestion), true);

  const save = lifecycle.beginSave();
  assert.ok(save);
  assert.equal(lifecycle.beginSave(), null);
  assert.equal(lifecycle.beginSuggestion(), null);
  assert.equal(lifecycle.finishSave(save), true);
  assert.ok(lifecycle.beginSuggestion());
});

test('title editor reducer preserves edits and candidates across failures and regeneration', () => {
  let state = titleRuntime.createTitleEditorState();
  state = titleRuntime.titleEditorReducer(state, { type: 'start', input: '初始标题' });
  state = titleRuntime.titleEditorReducer(state, {
    type: 'generate-success', suggestions: ['候选一', '候选二', '候选三'],
  });
  state = titleRuntime.titleEditorReducer(state, { type: 'change-input', value: '人工输入' });
  const beforeFailure = state;
  state = titleRuntime.titleEditorReducer(state, { type: 'generate-failure', error: '生成失败' });
  assert.equal(state.input, '人工输入');
  assert.deepEqual(state.suggestions, beforeFailure.suggestions);

  state = titleRuntime.titleEditorReducer(state, {
    type: 'generate-success', suggestions: ['新一', '新二', '新三'],
  });
  assert.equal(state.input, '人工输入', 'regeneration must not overwrite current input');
  assert.deepEqual(state.suggestions, ['新一', '新二', '新三']);
  state = titleRuntime.titleEditorReducer(state, { type: 'save-failure', error: '保存失败' });
  assert.equal(state.input, '人工输入');
  assert.deepEqual(state.suggestions, ['新一', '新二', '新三']);
});

test('title editor reducer closes after a successful save', () => {
  let state = titleRuntime.createTitleEditorState();
  state = titleRuntime.titleEditorReducer(state, { type: 'start', input: '标题' });
  state = titleRuntime.titleEditorReducer(state, { type: 'save-start' });
  titleRuntime.completeTitleSave(
    { id: 'event-a', title: 'Original', title_cn: '标题' },
    {
      onSaved: () => undefined,
      onSuccess: () => undefined,
      onClose: () => {
        state = titleRuntime.titleEditorReducer(state, { type: 'close' });
      },
    },
  );
  assert.equal(state.open, false);
  assert.equal(state.saving, false);
  assert.equal(state.error, '');
});

test('save success callbacks close outside request error normalization', () => {
  const callbackError = new Error('callback detail');
  let succeeded = 0;
  let closed = 0;
  assert.throws(() => titleRuntime.completeTitleSave(
    { id: 'event-a', title: 'Original', title_cn: '标题' },
    {
      onSaved: () => { throw callbackError; },
      onSuccess: () => { succeeded += 1; },
      onClose: () => { closed += 1; },
    },
  ), (reason) => reason === callbackError);
  assert.equal(succeeded, 1);
  assert.equal(closed, 1);
});

test('title editor hook uses the executable title lifecycle coordinator', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');

  assert.match(hook, /const lifecycleRef = useRef\(createTitleEditorLifecycle\(\)\)/);
  assert.match(hook, /lifecycleRef\.current\.beginSuggestion\(\)/);
  assert.match(hook, /lifecycleRef\.current\.beginSave\(\)/);
  assert.match(hook, /useReducer\(titleEditorReducer, undefined, createTitleEditorState\)/);
});

test('title editor start, close, input, and suggestion selection preserve explicit editing', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  const start = hook.slice(hook.indexOf('const start ='), hook.indexOf('const close ='));
  const close = hook.slice(hook.indexOf('const close ='), hook.indexOf('const changeInput ='));
  const change = hook.slice(hook.indexOf('const changeInput ='), hook.indexOf('const selectSuggestion ='));
  const select = hook.slice(hook.indexOf('const selectSuggestion ='), hook.indexOf('const generate ='));

  assert.match(start, /event\.title_cn \|\| event\.title \|\| ''/);
  for (const action of [
    'lifecycleRef.current.abortRequests()',
    "dispatch({ type: 'start', input: initialInput })",
  ]) assert.ok(start.includes(action), `start must include ${action}`);
  for (const action of [
    'lifecycleRef.current.abortRequests()',
    "dispatch({ type: 'close' })",
  ]) assert.ok(close.includes(action), `close must include ${action}`);
  assert.match(change, /dispatch\(\{ type: 'change-input', value \}\)/);
  assert.match(select, /dispatch\(\{ type: 'select-suggestion', value \}\)/);
  assert.doesNotMatch(select, /saveDisplayTitle/);
});

test('title editor generation and saving enforce validation, current tokens, and non-overwrite semantics', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  const generate = hook.slice(hook.indexOf('const generate ='), hook.indexOf('const save ='));
  const save = hook.slice(hook.indexOf('const save ='), hook.indexOf('useEffect('));

  assert.match(generate, /requestTitleSuggestions\(eventId, token\.signal, apiFetch\)/);
  assert.ok((generate.match(/lifecycleRef\.current\.isSuggestionCurrent\(token\)/g) || []).length >= 2);
  assert.match(generate, /dispatch\(\{ type: 'generate-success', suggestions: nextSuggestions \}\)/);
  assert.match(generate, /errorName\(reason\) !== 'AbortError'/);

  assert.match(save, /const validation = titleValidationError\(value\)/);
  assert.match(save, /saveDisplayTitle\(eventId, value, token\.signal, apiFetch\)/);
  assert.ok((save.match(/lifecycleRef\.current\.isSaveCurrent\(token\)/g) || []).length >= 1);
  const requestCatchEnd = save.indexOf('\n    if (!lifecycleRef.current.isSaveCurrent(token))');
  assert.notEqual(requestCatchEnd, -1);
  assert.ok(save.indexOf('completeTitleSave(', requestCatchEnd) > requestCatchEnd);
});

test('title editor closes on event changes and unmount cleanup only aborts', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  const hookBody = hook.slice(hook.indexOf('export function useTitleEditor'));
  const effects = hook.slice(hook.indexOf('useLayoutEffect('));
  const beforeLayoutEffect = hookBody.slice(0, hookBody.indexOf('useLayoutEffect('));

  assert.doesNotMatch(hookBody, /^\s*inputRef\.current = input;$/m);
  assert.doesNotMatch(hookBody, /^\s*activeEventIdRef\.current = activeEventId;$/m);
  assert.doesNotMatch(beforeLayoutEffect, /commitActiveEvent\(/);
  assert.match(effects, /lifecycleRef\.current\.commitActiveEvent\(activeEventId\)/);
  assert.match(effects, /inputRef\.current = ''/);
  assert.match(effects, /dispatch\(\{ type: 'active-event-changed' \}\)/);
  assert.match(effects, /\}, \[activeEventId\]\)/);
  assert.match(effects, /return \(\) => \{[\s\S]*lifecycleRef\.current\.destroy\(\)[\s\S]*\}/);
  const cleanup = effects.match(/return \(\) => \{([\s\S]*?)\};/)?.[1] || '';
  assert.doesNotMatch(cleanup, /set[A-Z]/);
});
