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
