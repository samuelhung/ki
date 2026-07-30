import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  loadPureDeclarations,
  readSourceModules,
} from '../detailPageContractTestUtils.mjs';

const hookUrl = new URL('./useTranscriptWorkflow.ts', import.meta.url);
const hookModules = readSourceModules([hookUrl]);
const {
  conflictMessage,
  createSegmentGuard,
  createTranscriptApi,
  createTranscriptSelectionOwner,
  isTranscriptAbortError,
  segmentationPollDelay,
} = loadPureDeclarations(hookModules, [
  'conflictMessage',
  'createSegmentGuard',
  'createTranscriptApi',
  'createTranscriptSelectionOwner',
  'isTranscriptAbortError',
  'segmentationPollDelay',
]);

test('transcript API client emits exact event-scoped requests', async () => {
  const calls = [];
  const request = async (url, options = {}) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => ({ id: 'ok' }) };
  };
  const api = createTranscriptApi(request);
  const signal = new AbortController().signal;

  await api.load('evt-1', signal);
  await api.loadRevision('evt-1', 'tr-1', signal);
  await api.saveManual('evt-1', '人工正文', 'tr-1');
  await api.startSegmentation('evt-1', 'tr-2');
  await api.loadTask('evt-1', 'task-1', signal);
  await api.confirmSegmentation('evt-1', 'task-1');
  await api.restoreRevision('evt-1', 'tr-1', 'tr-3');

  assert.deepEqual(calls.map(({ url, options }) => [url, options.method || 'GET']), [
    ['/api/events/evt-1/transcript', 'GET'],
    ['/api/events/evt-1/transcript/revisions/tr-1', 'GET'],
    ['/api/events/evt-1/transcript/manual', 'PUT'],
    ['/api/events/evt-1/transcript/segment', 'POST'],
    ['/api/events/evt-1/transcript/segment/task-1', 'GET'],
    ['/api/events/evt-1/transcript/segment/task-1/confirm', 'POST'],
    ['/api/events/evt-1/transcript/revisions/tr-1/restore', 'POST'],
  ]);
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    content: '人工正文', base_revision_id: 'tr-1',
  });
  assert.deepEqual(JSON.parse(calls[3].options.body), { base_revision_id: 'tr-2' });
  assert.deepEqual(JSON.parse(calls[6].options.body), { base_revision_id: 'tr-3' });
});

test('event selection invalidates A-to-B polling and stale A responses', () => {
  const owners = createTranscriptSelectionOwner();
  const firstA = owners.select('event-a');
  const eventB = owners.select('event-b');
  const currentA = owners.select('event-a');

  assert.equal(owners.isCurrent(firstA), false);
  assert.equal(owners.isCurrent(eventB), false);
  assert.equal(owners.isCurrent(currentA), true);
});

test('duplicate segmentation is blocked until the active request ends', () => {
  const guard = createSegmentGuard();
  assert.equal(guard.begin('event-a'), true);
  assert.equal(guard.begin('event-a'), false);
  assert.equal(guard.begin('event-b'), true);
  guard.end('event-a');
  assert.equal(guard.begin('event-a'), true);
});

test('409 maps to refresh-required copy and hook resets dialog state on event change', () => {
  assert.deepEqual(conflictMessage(409), {
    message: '原文已更新，请刷新后重试', refreshRequired: true,
  });
  assert.deepEqual(conflictMessage(500), {
    message: '操作失败，请稍后重试', refreshRequired: false,
  });
  assert.deepEqual(conflictMessage(410), {
    message: '分段结果已过期，请重新生成', refreshRequired: false,
  });

  const source = readFileSync(new URL('./useTranscriptWorkflow.ts', import.meta.url), 'utf8');
  assert.match(source, /setEditorOpen\(false\)/);
  assert.match(source, /setComparisonOpen\(false\)/);
  assert.match(source, /setHistoryOpen\(false\)/);
  assert.match(source, /pollLifecycle\.current\.abort\(\)/);
  assert.match(source, /abortableDelay\(delay, owner\.signal\)/);
});

test('cancelled requests and strict segmentation deadlines cannot leak across events', () => {
  assert.equal(isTranscriptAbortError(new DOMException('cancelled', 'AbortError')), true);
  assert.equal(isTranscriptAbortError({ name: 'AbortError', kind: 'cancelled' }), true);
  assert.equal(isTranscriptAbortError({ name: 'ApiRequestError', kind: 'timeout' }), false);
  assert.equal(segmentationPollDelay(1_000, 2_000), 1_000);
  assert.equal(segmentationPollDelay(1_950, 2_000), 50);
  assert.equal(segmentationPollDelay(2_000, 2_000), 0);

  const source = readFileSync(new URL('./useTranscriptWorkflow.ts', import.meta.url), 'utf8');
  for (const reset of ['setSaving(false)', 'setSegmenting(false)', 'setConfirming(false)', 'setHistoryLoading(false)', 'setRestoring(false)']) {
    assert.match(source, new RegExp(reset.replace(/[()]/g, '\\$&')));
  }
  const closeComparison = source.match(/const closeComparison[\s\S]*?\}, \[[^\]]*\]\);/)?.[0] || '';
  assert.match(closeComparison, /pollLifecycle\.current\.abort/);
  assert.doesNotMatch(closeComparison, /segmentGuard\.current\.end/);
  assert.equal(source.match(/segmentGuard\.current\.end/g)?.length, 1, 'only the active run may release its guard');
  assert.match(source, /selectionOwner\.current\.isCurrent\(selection\)[\s\S]{0,100}setRequestError\(reason\)/);
  assert.match(source, /abortableDelay\(delay, owner\.signal\)/);
});
