import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import test from 'node:test';

const workspaceUrl = new URL('./briefingWorkspace.mjs', import.meta.url);

test('selectBriefingId keeps a valid selection and otherwise chooses the newest item', async () => {
  assert.equal(existsSync(workspaceUrl), true, 'briefingWorkspace.mjs should exist');
  const { selectBriefingId } = await import(workspaceUrl);
  const items = [{ id: 'briefing-new' }, { id: 'briefing-old' }];

  assert.equal(selectBriefingId(items, 'briefing-old'), 'briefing-old');
  assert.equal(selectBriefingId(items, 'missing'), 'briefing-new');
  assert.equal(selectBriefingId([], 'briefing-old'), '');
});

test('selectBriefingId tolerates malformed history payloads', async () => {
  assert.equal(existsSync(workspaceUrl), true, 'briefingWorkspace.mjs should exist');
  const { selectBriefingId } = await import(workspaceUrl);

  assert.equal(selectBriefingId(null, 'briefing-old'), '');
  assert.equal(selectBriefingId([null, { id: '' }, { id: 'briefing-valid' }], ''), 'briefing-valid');
});

test('pending generated selection survives refresh failure and is consumed by a successful retry', async () => {
  const { resolveBriefingLoadSelection } = await import(workspaceUrl);

  const failedRefresh = resolveBriefingLoadSelection({
    items: [{ id: 'briefing-old' }],
    currentId: 'briefing-old',
    pendingPreferredId: 'briefing-generated',
    succeeded: false,
  });
  assert.deepEqual(failedRefresh, {
    selectedId: 'briefing-old',
    pendingPreferredId: 'briefing-generated',
  });

  const successfulRetry = resolveBriefingLoadSelection({
    items: [{ id: 'briefing-generated' }, { id: 'briefing-old' }],
    currentId: failedRefresh.selectedId,
    pendingPreferredId: failedRefresh.pendingPreferredId,
    succeeded: true,
  });
  assert.deepEqual(successfulRetry, {
    selectedId: 'briefing-generated',
    pendingPreferredId: '',
  });
});

test('successful stale history preserves a pending generated id until it is returned', async () => {
  const { resolveBriefingLoadSelection } = await import(workspaceUrl);

  const staleSuccess = resolveBriefingLoadSelection({
    items: [{ id: 'briefing-old' }],
    currentId: 'briefing-old',
    pendingPreferredId: 'briefing-generated',
    succeeded: true,
  });

  assert.deepEqual(staleSuccess, {
    selectedId: 'briefing-old',
    pendingPreferredId: 'briefing-generated',
  });

  assert.deepEqual(resolveBriefingLoadSelection({
    items: [{ id: 'briefing-generated-copy' }],
    currentId: 'briefing-generated-copy',
    pendingPreferredId: 'briefing-generated',
    succeeded: true,
  }), {
    selectedId: 'briefing-generated-copy',
    pendingPreferredId: 'briefing-generated',
  });
});

test('briefingMetrics reports type, generated time, topic count, and event count', async () => {
  assert.equal(existsSync(workspaceUrl), true, 'briefingWorkspace.mjs should exist');
  const { briefingMetrics } = await import(workspaceUrl);

  assert.deepEqual(briefingMetrics({
    type: 'daily',
    created_at: '2026-07-19 09:30:00',
    events_used: 7,
    topics: [{ topic: '格局' }, { topic: '前瞻' }],
  }), {
    typeLabel: '深度日报',
    generatedAt: '2026-07-19 09:30:00',
    topicCount: 2,
    eventCount: 7,
  });
});

test('briefingMetrics returns stable empty metrics for unavailable detail', async () => {
  assert.equal(existsSync(workspaceUrl), true, 'briefingWorkspace.mjs should exist');
  const { briefingMetrics } = await import(workspaceUrl);

  assert.deepEqual(briefingMetrics(null), {
    typeLabel: '即时快报',
    generatedAt: '',
    topicCount: 0,
    eventCount: 0,
  });
});
