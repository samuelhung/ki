import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
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

test('title editor hook keeps suggestion and save request ownership independent', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');

  assert.match(hook, /const suggestionOwnerRef = useRef\(createTitleRequestOwner\(\)\)/);
  assert.match(hook, /const saveOwnerRef = useRef\(createTitleRequestOwner\(\)\)/);
  assert.match(hook, /suggestionOwnerRef\.current\.start\(eventId\)/);
  assert.match(hook, /saveOwnerRef\.current\.start\(eventId\)/);
});

test('title editor start, close, input, and suggestion selection preserve explicit editing', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  const start = hook.slice(hook.indexOf('const start ='), hook.indexOf('const close ='));
  const close = hook.slice(hook.indexOf('const close ='), hook.indexOf('const changeInput ='));
  const change = hook.slice(hook.indexOf('const changeInput ='), hook.indexOf('const selectSuggestion ='));
  const select = hook.slice(hook.indexOf('const selectSuggestion ='), hook.indexOf('const generate ='));

  assert.match(start, /event\.title_cn \|\| event\.title \|\| ''/);
  for (const reset of [
    'suggestionOwnerRef.current.abort()',
    'saveOwnerRef.current.abort()',
    'setSuggestions([])',
    'setSelectedTitle(null)',
    "setError('')",
    'setGenerating(false)',
    'setSaving(false)',
    'setOpen(true)',
  ]) assert.ok(start.includes(reset), `start must include ${reset}`);
  for (const action of [
    'suggestionOwnerRef.current.abort()',
    'saveOwnerRef.current.abort()',
    'setOpen(false)',
    'setGenerating(false)',
    'setSaving(false)',
    "setError('')",
  ]) assert.ok(close.includes(action), `close must include ${action}`);
  assert.match(change, /setInput\(value\)/);
  assert.match(change, /suggestions\.includes\(value\) \? value : null/);
  assert.match(change, /setError\(''\)/);
  assert.match(select, /setInput\(value\)/);
  assert.match(select, /setSelectedTitle\(value\)/);
  assert.doesNotMatch(select, /saveDisplayTitle/);
});

test('title editor generation and saving enforce validation, current tokens, and non-overwrite semantics', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  const generate = hook.slice(hook.indexOf('const generate ='), hook.indexOf('const save ='));
  const save = hook.slice(hook.indexOf('const save ='), hook.indexOf('useEffect('));

  assert.match(generate, /if \(generating \|\| saving\) return/);
  assert.match(generate, /requestTitleSuggestions\(eventId, token\.signal, apiFetch\)/);
  assert.ok((generate.match(/suggestionOwnerRef\.current\.isCurrent\(token\)/g) || []).length >= 2);
  assert.doesNotMatch(generate, /setInput\(/);
  assert.match(generate, /setSuggestions\(nextSuggestions\)/);
  assert.match(generate, /const currentInput = inputRef\.current/);
  assert.match(generate, /setSelectedTitle\(nextSuggestions\.includes\(currentInput\) \? currentInput : null\)/);
  assert.match(generate, /errorName\(reason\) !== 'AbortError'/);

  assert.match(save, /if \(saving \|\| generating\) return/);
  assert.match(save, /const validation = titleValidationError\(input\)/);
  assert.match(save, /saveDisplayTitle\(eventId, input, token\.signal, apiFetch\)/);
  assert.ok((save.match(/saveOwnerRef\.current\.isCurrent\(token\)/g) || []).length >= 2);
  assert.match(save, /onSaved\(result\.id, result\.title_cn\)/);
  assert.match(save, /onSuccess\(\)/);
  assert.match(save, /close\(\)/);
});

test('title editor closes on event changes and unmount cleanup only aborts', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  const effects = hook.slice(hook.indexOf('useEffect('));

  assert.match(effects, /\}, \[activeEventId\]\)/);
  assert.match(effects, /return \(\) => \{[\s\S]*suggestionOwnerRef\.current\.abort\(\)[\s\S]*saveOwnerRef\.current\.abort\(\)[\s\S]*\}/);
  const cleanup = effects.match(/return \(\) => \{([\s\S]*?)\};/)?.[1] || '';
  assert.doesNotMatch(cleanup, /set[A-Z]/);
});
